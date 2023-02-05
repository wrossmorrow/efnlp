package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"reflect"
	"strings"

	"github.com/apache/beam/sdks/v2/go/pkg/beam"
	"github.com/apache/beam/sdks/v2/go/pkg/beam/io/bigqueryio"
	"github.com/apache/beam/sdks/v2/go/pkg/beam/io/textio"
	"github.com/apache/beam/sdks/v2/go/pkg/beam/register"
	"github.com/apache/beam/sdks/v2/go/pkg/beam/transforms/stats"
	"github.com/apache/beam/sdks/v2/go/pkg/beam/x/beamx"
)

/*

go run charcount.go \
	--project efnlp-naivegpt \
	--input bq://efnlp-naivegpt:enwiki20201020.rawtxt \
	--output counts \
	--limit 10

go run charcount.go \
	--project efnlp-naivegpt \
	--input bq://efnlp-naivegpt:enwiki20201020.rawtxt \
	--output bq://efnlp-naivegpt:enwiki20201020.rawcharcounts

*/

var (
	// Set this required option to specify where to read input from.
	//
	//		gs://... for cloud storage
	//		bq://<project_id>:<dataset>.<table> for bigquery
	//
	input = flag.String("input", "", "Input file (required).")

	// Set this required option to specify where to write the output.
	//
	//		gs://... for cloud storage
	//		bq://<project_id>:<dataset>.<table> for bigquery
	//
	output = flag.String("output", "", "Output file (required).")

	version = flag.Int("version", 0, "Pipeline version to run")
	limit = flag.Int("limit", 0, "Limit query (optional, <=0 is no limit)")
	dryrun = flag.Bool("dry-run", false, "Don't actually run beam job")
)

type WikiArticleJSON struct {
	Src   string `json:"src" bigquery:"src"`
	Id    string `json:"id" bigquery:"id"`
	Title string `json:"title" bigquery:"title"`
	Text  string `json:"text" bigquery:"text"`
}

type CharacterCounter struct {
	Ignore string
}

func (f *CharacterCounter) ProcessElement(
	ctx context.Context,
	article WikiArticleJSON,
	emit func(string),
) {
	text := article.Text
	if len(f.Ignore) > 0 {
		for _, r := range text {
			if !strings.Contains(f.Ignore, string(r)) {
				emit(string(r))
			}
		}
	} else {
		for _, r := range text {
			emit(string(r))
		}
	}
}

type CharCount struct {
	Char  string `json:"char" bigquery:"char"`
	Count int    `json:"count" bigquery:"count"`
}

type CharsAndCounts struct {
	Data map[string]int `json:"data"`
}

type MapCharacterCounter struct {
	Ignore string
}

func (f *MapCharacterCounter) ProcessElement(
	ctx context.Context,
	article WikiArticleJSON,
	emit func(CharsAndCounts),
) {
	m := make(map[string]int)
	text := article.Text
	if len(f.Ignore) > 0 {
		for _, r := range text {
			if !strings.Contains(f.Ignore, string(r)) {
				c := string(r)
				_, ex := m[c]
				if ex {
					m[c] += 1
				} else {
					m[c] = 1
				}
			}
		}
	} else {
		for _, r := range text {
			c := string(r)
			_, ex := m[c]
			if ex {
				m[c] += 1
			} else {
				m[c] = 1
			}
		}
	}

	emit(CharsAndCounts{Data: m})

	// i := 0
	// l := make([]CharCounts, len(m))
	// for s, c := range m {
	// 	l[i] = CharCount{Char: s, Count: c}
	// 	i++
	// }
	// emit(l)
}

func CountChars(s beam.Scope, text beam.PCollection) beam.PCollection {
	s = s.Scope("CountChars")
	chars := beam.ParDo(s, &CharacterCounter{Ignore: ""}, text)
	// GroupByKey? Is a stats.Count not a GroupBy?
	return stats.Count(s, chars)
}

func mergeCharCountMaps(a, b CharsAndCounts) CharsAndCounts {
	m := make(map[string]int)
	for s, c := range a.Data {
		m[s] = c
	}
	for s, c := range b.Data {
		_, ex := m[s]
		if !ex {
			m[s] = c
		} else {
			m[s] += c
		}
	}
	return CharsAndCounts{Data: m}
}

func textFormatFn(s string, c int) string {
	return fmt.Sprintf("%s: %v", s, c)
}

func ccFormatFn(cc CharCount) string {
	return textFormatFn(cc.Char, cc.Count)
}

func bqFormatFn(s string, c int) CharCount {
	return CharCount{Char: s, Count: c}
}

// func bqFormatFnMap(m map[string]int) []CharCount {
// 	l := make([]CharCount, len(m))
// 	i := 0
// 	for s, c := range m {
// 		l[i] = bqFormatFn(s, c)
// 		i++
// 	}
// 	return l
// }

type MapCharacterEmitter struct {}

func (f *MapCharacterEmitter) ProcessElement(
	ctx context.Context,
	counts CharsAndCounts,
	emit func(CharCount),
) {
	for s, c := range counts.Data {
		emit(bqFormatFn(s, c))
	}
}

// beam registrations
func init() {
	register.DoFn3x0[context.Context, WikiArticleJSON, func(string)](&CharacterCounter{})
	register.DoFn3x0[context.Context, WikiArticleJSON, func(CharsAndCounts)](&MapCharacterCounter{})
	register.DoFn3x0[context.Context, CharsAndCounts, func(CharCount)](&MapCharacterEmitter{})
	register.Function2x1(textFormatFn)
	register.Function2x1(bqFormatFn)
	register.Function1x1(ccFormatFn)
	register.Function2x1(mergeCharCountMaps)
	register.Emitter1[string]()
	register.Emitter1[CharsAndCounts]()
	register.Emitter1[CharCount]()
}

func main() {

	// If beamx or Go flags are used, flags must be parsed first.
	flag.Parse()

	prjFlag := flag.Lookup("project")
	if prjFlag == nil {
		log.Fatal("--project not provided")
	}
	project := prjFlag.Value.String()

	beam.Init()

	if *input == "" {
		log.Fatal("No input provided")
	}
	if *output == "" {
		log.Fatal("No output provided")
	}

	p := beam.NewPipeline()
	s := p.Root()

	// if strings.HasPrefix(*input, "gs://") {
	// 	formatted := beam.ParDo(s, JSONLineFormat, disaggd)
	// 	textio.Write(s, *output, formatted)
	// } else if strings.HasPrefix(*input, "bq://") {
	// 	bigqueryio.Write(s, project, (*output)[5:], disaggd)
	// } else {
	// 	formatted := beam.ParDo(s, JSONLineFormat, disaggd)
	// 	textio.Write(s, *output, formatted)
	// }

	inputTable := (*input)[5:]
	q := fmt.Sprintf("SELECT text FROM [%s]", inputTable)
	if *limit > 0 {
		q += fmt.Sprintf(" LIMIT %d", *limit)
	}
	q += ";"

	log.Printf("Running query: %s", q)
	log.Printf("Pipeline version: %d", *version)

	if !(*dryrun) {

		// always read text from BQ
		text := bigqueryio.Query(s, project, q, reflect.TypeOf(WikiArticleJSON{}))

		if *version == 0 {

			// seems weird to break up, but maybe we can see some parallelism?
			counted := beam.Reshuffle(s, CountChars(s, beam.Reshuffle(s, text)))
			if strings.HasPrefix(*output, "bq://") {
				outputTable := (*output)[5:]
				bqcounts := beam.ParDo(s, bqFormatFn, counted)
				bigqueryio.Write(s, project, outputTable, bqcounts)
			} else { // gs://, local
				formatted := beam.ParDo(s, textFormatFn, counted)
				textio.Write(s, *output, formatted)
			}

			// "A fusion break can be inserted after the following transforms to 
			// increase parallelism: bigquery.Query/bigqueryio.queryFn. The transforms 
			// had the following output-to-input element count ratio, respectively: 35783."
			// 
			// Still don't understand...

		} else if *version == 1 {

			// Plausible improvement (?): 
			// 
			// 		Don't emit chars, emit char counts in the text
			//		Those go in PCollection[map[char]int]
			//		Then merge [map[char]int]'s together (Combine?)
			// 		Then expand and write out
			//	
			maps := beam.ParDo(s, &MapCharacterCounter{}, beam.Reshuffle(s, text)) // PCollection[map[string]int]
			counted := beam.Combine(s, mergeCharCountMaps, maps) // (?) singleton PCollection[map[string]int]
			expanded := beam.Reshuffle(s, beam.ParDo(s, &MapCharacterEmitter{}, counted)) // PCollection[CharCount]
			
			if strings.HasPrefix(*output, "bq://") {
				outputTable := (*output)[5:]
				bigqueryio.Write(s, project, outputTable, expanded)
			} else {
				formatted := beam.ParDo(s, ccFormatFn, expanded)
				textio.Write(s, *output, formatted)
			}

		} else {
			log.Fatalf("Unknown version: %d", *version)
		}

		if err := beamx.Run(context.Background(), p); err != nil {
			log.Fatalf("Failed to execute job: %v", err)
		}

	}
}
