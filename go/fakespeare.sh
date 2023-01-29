#!/bin/bash
G=1000000
mkdir -p results
for B in 1 2 3 4 5 7 10 12 15 20 ; do
	printf "\nB = $B\n"
	go run *.go -parse \
		-input ../data/tinywillspeare.txt \
		-language ../cpp/language.proto.bin \
		-block $B \
		-generate $G \
		-print=false
done
