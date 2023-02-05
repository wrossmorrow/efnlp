default:
    just --list

name := "efnlp"
current_version := "v0.1.14"
current_tag := "draft-v0.1.14"

alias i := install
alias u := update
alias f := format
alias l := lint
alias t := unit-test
alias r := run
alias b := build
# alias p := publish

# install dependencies
install: 
    poetry install

# update dependencies
update: 
    poetry update

# protobuf generated code
codegen tag=current_tag:
    docker run --entrypoint /usr/bin/protoc \
        -v ${PWD}/proto:/efnlp/proto \
        -v ${PWD}/efnlp:/efnlp/local \
        us-central1-docker.pkg.dev/efnlp-naivegpt/dataflow/python:{{tag}} \
        -I/efnlp/proto --python_out=/efnlp/local /efnlp/proto/efnlp.proto

# format the code
format: 
    poetry run black {{name}}
    poetry run black test

# run mypy static type analysis
types: 
    poetry run mypy {{name}}

# lint the code
lint:
    poetry run black {{name}} test --check
    poetry run flake8 {{name}} test --exclude efnlp/efnlp_pb2.py
    poetry run mypy {{name}} test

# run all unit tests
unit-test *FLAGS:
    poetry run python -m pytest -v --disable-warnings \
        test/unit/test_parsing.py \
        {{FLAGS}}

# run CLI
run *FLAGS:
    poetry run python -m efnlp {{FLAGS}}

# bring up compose setup
up *FLAGS:
    docker-compose build && docker-compose up {{FLAGS}}

docker-shell tag=current_tag:
    docker run -it --entrypoint bash \
        -v ${PWD}/efnlp-naivegpt-eceba617e9fe.secret.json:/efnlp/gac.json \
        -e GOOGLE_APPLICATION_CREDENTIALS=/efnlp/gac.json \
        us-central1-docker.pkg.dev/efnlp-naivegpt/dataflow/python:{{tag}}

docker-python tag=current_tag:
    docker run -it --entrypoint python3 \
        -v ${PWD}/efnlp-naivegpt-eceba617e9fe.secret.json:/efnlp/gac.json \
        -e GOOGLE_APPLICATION_CREDENTIALS=/efnlp/gac.json \
        us-central1-docker.pkg.dev/efnlp-naivegpt/dataflow/python:{{tag}}

docker-beam tag=current_tag:
    docker run -it --entrypoint bash \
        -v ${PWD}/beam:/efnlp/beam \
        -v ${PWD}/efnlp-naivegpt-eceba617e9fe.secret.json:/efnlp/gac.json \
        -e GOOGLE_APPLICATION_CREDENTIALS=/efnlp/gac.json \
        us-central1-docker.pkg.dev/efnlp-naivegpt/dataflow/python:{{tag}}

docker-run command="" tag=current_tag:
    docker run --entrypoint bash \
        us-central1-docker.pkg.dev/efnlp-naivegpt/dataflow/python:{{tag}} \
        {{command}}

dataflow-build tag=current_tag:
    docker build . -f Dockerfile.pybeam \
        -t us-central1-docker.pkg.dev/efnlp-naivegpt/dataflow/python:{{tag}}

dataflow-push tag=current_tag:
    docker push us-central1-docker.pkg.dev/efnlp-naivegpt/dataflow/python:{{tag}}

# build package
build: 
    poetry build

# publish the package
publish *flags:
    poetry publish {{flags}}
