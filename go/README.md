
Build protobuf go code:
```shell
just codegen
```

Run server (after building a language/model in [`c++`](/../cpp)):
```shell
go run *.go -language ../cpp/language.proto.bin -model ../cpp/model.proto.bin 
```

Run client (with running server) and executing some ad-hoc tests
```shell
go run *.go -client
```
