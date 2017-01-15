FROM amazonlinux
MAINTAINER Pema Geyleg <pema@casecommons.org>
ARG project_name
LABEL application=${project_name}

# Install build dependencies
RUN yum install python27-pip gcc zip libffi-devel python27-devel openssl-devel -y && \
    pip install -U pip

# Copy source
COPY src /build/src
WORKDIR /build/src

# Install function dependencies
RUN pip install -t vendor/ -r requirements.txt --upgrade

# Create function archive
ARG function_name
RUN zip -9 -r ../${function_name}.zip * -x *.pyc