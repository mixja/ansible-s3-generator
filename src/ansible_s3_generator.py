#!/usr/bin/env python
import sys, os
parent_dir = os.path.abspath(os.path.dirname(__file__))
vendor_dir = os.path.join(parent_dir, 'vendor')
sys.path.append(vendor_dir)

from dulwich.client import get_transport_and_path
from dulwich.repo import Repo
import shutil
import urllib2
from collections import namedtuple
from ansible.parsing.dataloader import DataLoader
from ansible.vars import VariableManager
from ansible.inventory import Inventory
from ansible.executor.playbook_executor import PlaybookExecutor
import boto3
import json
from argparse import Namespace
from base64 import b64decode
import logging

# Configure logging
log = logging.getLogger()
log.setLevel(logging.INFO)

# Global/Environment variables
CLONE_FOLDER = '/tmp/working'
BUILD_FOLDER = '/tmp/build'
GIT_BRANCH = os.environ.get('GIT_BRANCH') or 'master'
GIT_USER = os.environ.get('GIT_USER')
GIT_PASSWORD = os.environ.get('GIT_PASSWORD')
PLAYBOOK_FILE = os.environ.get('PLAYBOOK_FILE') or CLONE_FOLDER + '/site.yml'
INVENTORY_FILE = os.environ.get('INVENTORY_FILE') or CLONE_FOLDER + '/inventory'
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_OBJECT = os.environ.get('S3_OBJECT')

# Get Authorization Handler
def get_auth_handler(git_url, username, password):
  password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
  password_mgr.add_password(None, git_url, username, password)
  handlers = [urllib2.HTTPBasicAuthHandler(password_mgr)]
  return urllib2.build_opener(*handlers)

# Clone repository
def clone_repo(git_url, git_revision, git_branch, opener):
  local = Repo.init(CLONE_FOLDER, mkdir=True)
  client, path = get_transport_and_path(git_url)
  if opener:
    client.opener = opener
  remote_refs = client.fetch(path, local, determine_wants=local.object_store.determine_wants_all)
  remote_refs[git_branch] = remote_refs[b"HEAD"] = str(git_revision)
  local.refs.import_refs(b'refs/remotes/origin',{n[len(b'refs/heads/'):]: v for (n, v) in remote_refs.items() if n.startswith(b'refs/heads/')})
  local.refs.import_refs(b'refs/tags',{n[len(b'refs/tags/'):]: v for (n, v) in remote_refs.items() if n.startswith(b'refs/tags/')})
  local[b"HEAD"] = remote_refs[b"HEAD"]
  local.reset_index()
  return local

# Handle Event
def lambda_handler(event, context):
  # Get event data
  log.info('Received event %s' % str(event))
  message = json.loads(event['Records'][0]['Sns']['Message'], object_hook=lambda d: Namespace(**d))
  log.info('Received message %s' % str(message))
  
  ref = message.ref
  if ref != 'refs/heads/' + GIT_BRANCH:
    log.info('Event does not relate to configured branch %s - exiting' % GIT_BRANCH)
    return

  git_revision = message.after
  git_url = message.repository.clone_url
  git_repository = message.repository.name

  # Generate authorization header
  if GIT_USER and GIT_PASSWORD:
    git_password = boto3.client('kms').decrypt(CiphertextBlob=b64decode(GIT_PASSWORD))['Plaintext']
    opener = get_auth_handler(git_url, GIT_USER, git_password)
  else:
    opener = None

  # Clone git repository
  shutil.rmtree(CLONE_FOLDER,ignore_errors=True)
  local = clone_repo(git_url, git_revision, GIT_BRANCH, opener)
  
  # Run Ansible playbooks
  variable_manager = VariableManager()
  loader = DataLoader()
  inventory = Inventory(loader=loader, variable_manager=variable_manager,  host_list=INVENTORY_FILE)
  groups = list(set(inventory.list_groups()) - set(['all','ungrouped']))
  variable_manager.set_inventory(inventory)
  passwords = {}
  Options = namedtuple('Options', [
    'listtags', 'listtasks', 'listhosts', 'syntax', 
    'connection','module_path', 'forks', 'remote_user', 
    'private_key_file', 'ssh_common_args', 'ssh_extra_args', 'sftp_extra_args', 
    'scp_extra_args', 'become', 'become_method', 'become_user', 
    'verbosity', 'check', 'tags'
  ])
  options = Options(
    listtags=False, listtasks=False, listhosts=False, syntax=False, 
    connection='local', module_path=None, forks=1, remote_user=None, 
    private_key_file=None, ssh_common_args=None, ssh_extra_args=None, sftp_extra_args=None, 
    scp_extra_args=None, become=False, become_method=None, become_user=None, 
    verbosity=None, check=False, tags=['generate']
  )

  for group in groups:
    variable_manager.extra_vars = {
      'env': group,
      'sts_disable':'true',
      'cf_build_folder': BUILD_FOLDER
    }
    pbex = PlaybookExecutor(
      playbooks=[PLAYBOOK_FILE], 
      inventory=inventory, 
      variable_manager=variable_manager, 
      loader=loader, 
      options=options, 
      passwords=passwords
    )
    pbex.run()

  # S3 settings
  s3 = boto3.client('s3')
  s3_object = S3_OBJECT or git_repository + '.zip'

  # Archive generated files
  shutil.make_archive('/tmp/build','zip',BUILD_FOLDER)
  data = open('/tmp/build.zip','rb')

  # Put git archive to S3
  response = s3.put_object(Key=s3_object, Bucket=S3_BUCKET, Body=data)
  log.info('Published to S3 with response: %s' % str(response))

  # Cleanup
  data.close()
  os.remove('/tmp/build.zip')
  shutil.rmtree(CLONE_FOLDER,ignore_errors=True)
