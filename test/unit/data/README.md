
### GPT-2 

We use OpenAI's `encoder.json` from [`tiktoken`](https://github.com/openai/tiktoken) available [here](https://openaipublic.blob.core.windows.net/gpt-2/encodings/main/encoder.json), but add ` ` and `\n` as characters. Somehoe these aren't in that encoder, but it is hard to believe they don't enter into encoding text for analysis at OpenAI. 
