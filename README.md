# efnlp

This is the _jankiest possible_ take at computing n-gram or conditional empirical frequency ((C)EF) distributions for successor tokens given a fixed-width prefix. Yes that's just a Markov model. In a way this is _purposefully_ naive, and interested in how far such a naive technique goes. 

There's `python` and `c++` code (in [`efnlp`](/efnlp) and [`cpp`](/cpp) respectively) for analyzing text and creating sampling datastructures. There's also `go` code (in [`go`](/go)) for a gRPC server to read sampling datastructures and serve batch or streaming generated text. 

## Motivation (even though we just playin)

The basic idea is to explore computing these values and using them in generative sampling tasks. We "hypothesize" that the asymptotic (in data and model class universality) result of computational [(L)LMs](https://en.wikipedia.org/wiki/Language_model) is a high-fidelity representation of the (C)EF in the training data. This is a bit tautologous, for a consistent statistical model estimated on sufficient data. See `paper/*.pdf` for more; however I have had repeated personal experiences with really cool complicated models basically reducing to the information in counts and averages, much like (C)EFs. 

Of course, a (C)EF "model" should have serious generalizability challenges when confronted with valid sequences not appearing in the training data. Particularly if we wish to generate text (via token sequences), we may generate sequences purely by chance that have no (or limited) precedent and thus have limited predictive capacity. (A Markov model can always reduce to token occurrence frequencies, though randomly choosing tokens is far from language modeling.) This is a primary goal of statistical models: to find (or use) structure to "fill in the gaps" of a particular corpus of training data. However, as a training corpus grows to encompass more and more of the possibilities of discourse, the likelihood we have not "seen" a valid sequence should also decrease, and a model should also be getting progressively more aligned with the (C)EFs. 

Also we would expect the required storage for a purely (C)EF "model" to grow quite large. This is, in principal, another primary goal of statistical models: to "compress" statistical information without diminishing validation/generalization performance. Yet, the SOTA statistical models are themselves quite extraordinarily large; samples are not reasonable computable on a single machine, involving many billions of parameters and linear algebra involved enough to require specialized hardware. 

Obviously if simple (C)EF models were of comparable quality to modern LLMs they would be making all the noise instead. This isn't about a better approach, just a personal investigation. 

## Example 

You can run the `python` code from the CLI as
```shell
$ python -m efnlp -c data/tinywillspeare.txt -m -s -b 10 -g 100000 -o sample-results.txt
[2023-01-21T18:31:07.445610] Forming (character) language
[2023-01-21T18:31:07.491561] Encoding corpus
[2023-01-21T18:31:07.569177] Corpus is 1,115,393 tokens long
[2023-01-21T18:31:07.569217] Parsing prefix/follower tokens
[2023-01-21T18:31:41.985965] Normalizing to empirical frequencies
[2023-01-21T18:31:51.631065] Memory (roughly) required: 62.4 MB (about 8,183,314 dbl, 16,366,628 fl)
[2023-01-21T18:31:51.631112] Sampling and decoding 100000 tokens
[2023-01-21T18:31:52.810630] Writing sampled results to sample-results.txt
```
(for which you can see generated text in [`results`](/sample-results.txt)). The compiled `c++` is similar, 
```shell
cpp$ ./efnlp -c data/tinywillspeare.txt -m -s -b 10 -g 100000 -o sample-results.txt
```

Our "model" here (in `python`) is, more or less, 8M `double`s worth of "parameters" and "trains" (estimates) in a single process on an (old) macbook in under a minute (for 10-token sequence statistics). Sampling is basically constant time, relying on hashmaps; the example above takes about 0.1ms per character sampled (with zero code optimizations). The (C)EF "model" are a significant inflation of the data size: 1.1MB of data turns into 62.4MB of statistics. But honestly the results aren't that bad. It's junk of course, but on the surface comparable to generative text from a 10M parameter transformer style model applied to the same dataset that trained for 15 minutes on a GPU ([tweet here](https://twitter.com/karpathy/status/1615400286293753856?cxt=HHwWgIDUqY2Ah-ssAAAA), [code here](https://github.com/karpathy/nanoGPT)). 

The full CLI arg list can be reviewed from
```shell
$ python -m efnlp -h
```

More comprehensive results are detailed in the following table (see `paper/*.pdf` for more discussion): 

| B | \# prefixes | r(B) | \# patterns | s(B) | avg &tau; | space | parse | gen/&tau; | parse | gen/&tau; |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 65 | 0.0\% | 1,403 | 0.1\% | 21.6 | 3kB | 1.0s | 1.8&mu;s | 51ms | 0.1&mu;s |
| 2 | 1,403 | 0.1\% | 11,556 | 1.0\% | 8.2 | 36kB | 2.0s | 1.8&mu;s | 151ms | 0.1&mu;s |
| 3 | 11,556 | 1.0\% | 50,712 | 4.5\% | 4.4 | 221kB | 3.3s | 2.5&mu;s | 297ms | 0.4&mu;s |
| 4 | 50,712 | 4.5\% | 141,021 | 12.6\% | 2.8 | 876kB | 4.3s | 3.2&mu;s | 561ms | 0.4&mu;s |
| 5 | 141,021 | 12.6\% | 283,313 | 25.4\% | 2.0 | 2.5MB | 6.4s | 3.6&mu;s | 1.2s | 0.5&mu;s |
| 7 | 447,352 | 40.1\% | 609,659 | 54.7\% | 1.4 | 10.1MB | 12.0s | 5.0&mu;s | 1.8s | 0.8&mu;s |
| 10 | 858,920 | 77.0\% | 937,254 | 84.0\% | 1.1 | 31.9MB | 28.0s | 7.2&mu;s | 3.4s | 1.1&mu;s |
| 12 | 991,391 | 88.9\% | 1,027,857 | 92.2\% | 1.0 | 50.4MB | 37.3s | 8.3&mu;s | 4.1s | 1.2&mu;s |
| 15 | 1,069,423 | 95.9\% | 1,081,060 | 96.9\% | 1.0 | 80.6MB | 54.3s | 10.0&mu;s | 5.4s | 1.4&mu;s |
| 20 | 1,103,358 | 98.9\% | 1,106,345 | 99.2\% | 1.0 | 133MB | 129.0s | 42.7&mu;s | 7.8s | 1.5&mu;s |


Note (until we get better formatting) that the first "parse" and "gen/&tau;" columns are for `python`, the second set are for `c++` (see `cpp` folder). With both `python` and compiled code we can generate text at O(&mu;s)/token. However compiled code seems to scale a bit better with longer sequences. With compiled codee we can parse out the (C)EFs in shakespeare in seconds; while `python` is still "reasonable" it takes a couple minutes to parse 20-token sequences. 

## Usage

### python

See [`efnlp/__main__.py`](/efnlp/__main__.py) for an example of running the no-doubt-dumb implementations in [`efnlp/__init__.py`](/efnlp/__init__.py). 

### c++

See [`cpp/*`](/cpp), with stuff that should be ready for `cmake` to run through a build. Embarassingly, pretty much everything is just in [`main.cpp`](/cpp/main.cpp). 

### go

See [`go/*`](/go), with stuff that should be ready to build. There's a very brief [`README.md`](/go/README.md) 

