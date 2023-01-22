# efnlp

This is the _jankiest possible_ take at computing n-gram or conditional empirical frequency ((C)EF) distributions for successor tokens given a fixed-width prefix. In a way it's purposefully naive, and interested in how far such a naive technique goes. 

The basic idea is to explore computing these values and using them in generative sampling tasks. We "hypothesize" that the asymptotic (in data and model class universality) result of computational [(L)LMs](https://en.wikipedia.org/wiki/Language_model) is a high-fidelity representation of the (C)EF in the training data. This is a bit tautologous, for a consistent statistical model estimated on sufficient data. See `paper/*.pdf` for more. 

Of course, a (C)EF "model" should have serious generalizability challenges when confronted with valid sequences not appearing in the training data. Particularly if we wish to generate text (via token sequences), we may generate sequences purely by chance that have no (or limited) precedent and thus have limited predictive capacity. However, as the training corpus grows to encompass more and more of the possibilities of discourse, the likelihood we have not "seen" a valid sequence must also decrease, while the model should also be getting progressively more aligned with the (C)EFs. 

Also we would expect the required storage for a purely (C)EF "model" to grow quite large. This is a primary goal of statistical models. Yet, the SOTA statistical models are themselves quite extraordinarily large; samples are not reasonable computable on a single machine, involving many billions of parameters and linear algebra involved enough to require specialized hardware. 

Obviously if simple (C)EF models were of comparable quality to modern LLMs they would be making all the noise instead. This isn't about a better approach, just a personal investigation. 

## Example 

You can run this code from the CLI as
```shell
$ python -m efnlp -c data/tinywillspeare.txt -m -b 10 -g 100000 -o sample-results.txt
[2023-01-21T18:31:07.445610] Forming (character) language
[2023-01-21T18:31:07.491561] Encoding corpus
[2023-01-21T18:31:07.569177] Corpus is 1,115,393 tokens long
[2023-01-21T18:31:07.569217] Parsing prefix/follower tokens
[2023-01-21T18:31:41.985965] Normalizing to empirical frequencies
[2023-01-21T18:31:51.631065] Memory (roughly) required: 62.4 MB (about 8,183,314 dbl, 16,366,628 fl)
[2023-01-21T18:31:51.631112] Sampling and decoding 100000 tokens
[2023-01-21T18:31:52.810630] Writing sampled results to sample-results.txt
```
(and you can see results in [`sample-results.txt`](/sample-results.txt)). Our "model" is, more or less, 8M `double`s worth of "parameters" and "trains" (estimates) in a single process on an (old) macbook in under a minute. Sampling is basically constant time, relying on hashmaps; the example above takes about 0.1ms per character sampled (with zero code optimizations). The (C)EF "model" are a significant inflation of the data size: 1.1MB of data turns into 62.4MB of statistics. But honestly the results aren't that bad. It's junk of course, but on the surface comparable to generative text from a 10M parameter transformer style model applied to the same dataset that trained for 15 minutes on a GPU ([tweet here](https://twitter.com/karpathy/status/1615400286293753856?cxt=HHwWgIDUqY2Ah-ssAAAA), [code here](https://github.com/karpathy/nanoGPT)). 

The full CLI arg list can be reviewed from
```shell
$ python -m efnlp -h
```

## Usage

See [`__main__.py`](/efnlp/__main__.py) for an example of running the no-doubt-dumb implementations in `__init__.py`. 
