default:
    just --list

name := "efnlp"

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

# format the code
format: 
    poetry run black {{name}}
    poetry run black test

# run mypy static type analysis
types: 
    poetry run mypy {{name}}

# lint the code
lint:
    poetry run black {{name}} test --check --exclude env
    poetry run flake8 {{name}} test
    poetry run mypy {{name}} test

# run all unit tests
unit-test *flags:
    poetry run python -m pytest -v \
        test/unit \
        --disable-warnings \
        {{flags}}

# run all solver tests
solver-test *flags:
    poetry run python -m pytest -v \
        test/solver \
        --disable-warnings \
        {{flags}}
            
# run all integration tests
integration-test *flags:
    poetry run python -m pytest -v \
        test/integration \
        --disable-warnings \
        {{flags}}

# bring up compose setup
up *FLAGS:
    docker-compose build && docker-compose up {{FLAGS}}

# run CLI
run *flags:
    python -m efnlp {{flags}}

# build package
build: 
    poetry build

# publish the package
publish *flags:
    poetry publish {{flags}}
