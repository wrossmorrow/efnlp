
This is a `go` implementation of a gRPC service that can
* read a `protobuf` specified `Language` and model (`SuffixTreeSet`)
* return data about that language/model
* generate samples of text from a prompt
* stream generated text from a prompt

Build protobuf go code:
```shell
just codegen
```

Run server (after building a language/model in [`c++`](https://github.com/wrossmorrow/efnlp/tree/main/cpp)):
```shell
just run -language ../cpp/language.proto.bin -model ../cpp/model.proto.bin 
```
or
```shell
go run *.go -language ../cpp/language.proto.bin -model ../cpp/model.proto.bin 
```

Run client (with running server) and executing some ad-hoc tests
```shell
just run -client
```
or 
```shell
go run *.go -client
```
