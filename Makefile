# Project variables
export PROJECT_NAME ?= lambda-ansible-s3-generator

# Parameters
export FUNCTION_NAME ?= ansibleS3Generator
S3_BUCKET ?= 429614120872-cfn-lambda
AWS_DEFAULT_REGION ?= us-west-2

include Makefile.settings

.PHONY: build publish clean

test %:
	@ echo "$*:a"

build:
	@ ${INFO} "Creating lambda build..."
	@ docker-compose $(TEST_ARGS) build $(PULL_FLAG) lambda
	@ ${INFO} "Copying lambda build..."
	@ docker-compose $(TEST_ARGS) up lambda
	@ rm -rf build
	@ mkdir -p build
	@ docker cp $$(docker-compose $(TEST_ARGS) ps -q lambda):/build/$(FUNCTION_NAME).zip build/
	@ ${INFO} "Build complete"

publish:
	@ ${INFO} "Publishing $(FUNCTION_NAME).zip to s3://$(S3_BUCKET)..."
	@ aws s3 cp --quiet build/$(FUNCTION_NAME).zip s3://$(S3_BUCKET)
	@ ${INFO} "Published to S3 URL: https://s3.amazonaws.com/$(S3_BUCKET)/$(FUNCTION_NAME).zip"
	@ ${INFO} "S3 Object Version: $(S3_OBJECT_VERSION)"

clean:
	${INFO} "Destroying build environment..."
	@ docker-compose $(TEST_ARGS) down -v || true
	${INFO} "Removing dangling images..."
	@ $(call clean_dangling_images,$(PROJECT_NAME))
	@ ${INFO} "Removing all distributions..."
	@ rm -rf src/*.pyc src/vendor build
	${INFO} "Clean complete"