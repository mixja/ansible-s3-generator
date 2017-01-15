#!/bin/bash
rm -rf src/vendor
rm -rf src/*.py
mkdir -p build
cd src
pip install -t vendor/ -r requirements.txt --upgrade
zip -9 -r ../build/${FUNCTION_NAME}.zip * -x *.pyc