
This is a `go` implementation of a gRPC service that can
* read a `protobuf` specified `Language` and model (`SuffixTreeSet`)
* return data about that language/model
* generate samples of text from a prompt
* stream generated text from a prompt

Build `protobuf` `go` code:
```shell
just codegen
```
This uses [`buf`](https://buf.build/) not `protoc` (directly). 

Run the gRPC server (after building a language/model in [`c++`](https://github.com/wrossmorrow/efnlp/tree/main/cpp)) with
```shell
just run -language ../cpp/language.proto.bin -model ../cpp/model.proto.bin 
```
or
```shell
go run *.go -language ../cpp/language.proto.bin -model ../cpp/model.proto.bin 
```
The `language` and `model` files must be serialized `protobuf` from the specs here, and can be 
* local files or objects in S3 (passing names starting with `s3://`)
* `gz` compressed or not (`gz` compression can significantly reduce the stored size)

Run the gRPC client (assuming a server is running) and execute some ad-hoc tests with
```shell
just run -client
```
or 
```shell
go run *.go -client
```

You can also parse with 
```shell
just run -parse -input ../data/tinywillspeare.txt \
	-language ../cpp/language.proto.bin \
	-block 20 -model model20.proto.bin.gz
```
or 
```shell
go run *.go -parse -input ../data/tinywillspeare.txt \
	-language ../cpp/language.proto.bin \
	-block 20 -model model20.proto.bin.gz
```

There's a quick take at a `docker` setup here too. See `Dockerfile`. 
