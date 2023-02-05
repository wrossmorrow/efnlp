#include <getopt.h>
#include <unistd.h>

#include <cstdlib>
#include <cstdint>
#include <cassert>
#include <cerrno>
#include <cmath>
#include <chrono>
#include <iostream>
#include <fstream>
#include <list>
#include <map>
#include <random>
#include <stdexcept>
#include <sstream>
#include <string>
#include <vector>

#include "spdlog/spdlog.h"

#include "efnlp.pb.h" // Note: path depends on cmake config
#include "efnlp.hpp"

using namespace std; 

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * 

 Misc

 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

class Timer {
    chrono::system_clock::time_point s, e;

public:
    void tic() { s = now(); }

    chrono::system_clock::time_point now() {
        return chrono::system_clock::now();
    }

    double toc_s() {
        e = now();
        return chrono::duration_cast<std::chrono::seconds>(e-s).count();
    }

    double toc_ms() {
        e = now();
        return chrono::duration_cast<std::chrono::milliseconds>(e-s).count();
    }

    double toc_us() {
        e = now();
        return chrono::duration_cast<std::chrono::microseconds>(e-s).count();
    }

    double toc_ns() {
        e = now();
        return chrono::duration_cast<std::chrono::nanoseconds>(e-s).count();
    }
};

string readFile(ifstream * in) {
    string contents;
    if( in ) {
        in->seekg(0, std::ios::end);
        contents.resize(in->tellg());
        in->seekg(0, ios::beg);
        in->read(&contents[0], contents.size());
        return contents;
    }
    throw(errno);
}

string readFile(const char * filename) {
    ifstream in(filename, ios::in);
    return readFile(&in);
}

string readFile(string filename) {
    ifstream in(filename, ios::in);
    return readFile(&in);
}

int main(int argc, char *argv[]) {

    int B = 5, G = 0, N;
    bool stats = false, memory = false, verbose = true, dump = false, json = false;
    string filename, output, textprompt = " ";

    Timer timer = Timer();

    for(;;) {
        switch( getopt(argc, argv, "c:b:g:p:o:djsmqh") ) {

            // options
            case 'c': filename = optarg; continue;
            case 'b': B = atoi(optarg); continue;
            case 'g': G = atoi(optarg); continue;
            case 'p': textprompt = optarg; continue;
            case 'o': output = optarg; continue;

            // flags
            case 'd': dump = true; continue;
            case 'j': json = true; continue;
            case 's': stats = true; continue;
            case 'm': memory = true; continue;
            case 'q': verbose = false; continue;

            // help
            case '?':
            case 'h':
            default :
                cout << "Help/Usage Example\n";
                break;

            case -1: break;
        }

        break;
    }

    if( filename.length() == 0 ) {
        cout << "CLI requires an input filename\n";
        return 1;
    }

    if( verbose ) {
        cout << "\nRunning with:\n";
        cout << "  filename: " << filename << "\n";
        cout << "  blocksize: " << B << "\n";
        cout << "  generating: " << G << "\n";
        cout << "  prompt: \"" << textprompt << "\"\n";
        cout << "  output: " << output << "\n";
        if( dump )
            cout << "  dumping results" << (json ? " as json" : " as proto") << "\n";
        cout << "\n";
    }

    // Input file is read into memory once, with a double pass for finding
    // the char language and another for encoding. For very large files
    // the extra IO of multiple file reads might be better... but also 
    // we're presuming that we are parsing a CharLanguage from the text
    // as well as estimating it's (C)EFs. A more "production" implement-
    // ation would probably split those steps; or we could single-pass
    // language construction and estimation with some re-org. 

    if( verbose ) {
        spdlog::info("Reading input file");
    }

    timer.tic();
    string text = readFile(filename);
    if( verbose ) {
        spdlog::info("Timer:: Reading text us: {}", timer.toc_us());
    }

    if( verbose ) {
        if( stats ) {
            spdlog::info(
                "File is {} chars long ({:0.2f}MB)", 
                text.length(), 4.0f*text.length()/1024.0f/1024.0f
            );
        }
        spdlog::info("Parsing language");
    }

    timer.tic();
    CharLanguage L(text);
    if( verbose ) {
        spdlog::info("Timer:: Language parsing ms: {}", timer.toc_ms());
    }

    if( dump ) {

        if( json ) {

            if( verbose ) {
                spdlog::info("Serializing parsed language to JSON");
            }

            timer.tic();
            auto j = L.json();
            if( verbose ) {
                spdlog::info("Timer:: JSON serialization us: {:}", timer.toc_us());
            }

            ofstream ofs("language.json", ios_base::out);
            ofs << j;
            ofs.close();

        } else {

            if( verbose ) {
                spdlog::info("Serializing parsed language to protobuf");
            }

            timer.tic();
            auto L_proto = L.proto();
            if( verbose ) {
                spdlog::info("Timer:: Protobuf serialization us: {:}", timer.toc_us());
            }

            ofstream ofs("language.proto.bin", ios_base::out | ios_base::binary);
            L_proto.SerializeToOstream(&ofs);
            ofs.close();

            efnlp::PROTO_VERSION::Language CL_proto;

            ifstream in("language.proto.bin", ios::in | ios::binary);
            if( !CL_proto.ParseFromIstream(&in) ) {
                spdlog::error("Failed to deserialize written protobuf data");
            } else {
                timer.tic();
                CharLanguage CL = CharLanguage(&CL_proto);
                if( verbose ) 
                    spdlog::info("Timer:: Deserialized proto ms: {:}", timer.toc_ms());
            }
            in.close();

        }

    }

    if( verbose ){
        spdlog::info("Encoding corpus");
    }

    timer.tic();
    TokenString C = TokenString(text, &L);
    if( verbose ) {
        spdlog::info("Timer:: Encoding ms: {}", timer.toc_ms());
    }

    N = C.length();

    if( verbose ) {
        if( stats )
            spdlog::info("Stats:: Corpus is {} tokens long", N);
        spdlog::info("Parsing suffix tree");
    }

    timer.tic();
    Prefix p = Prefix(&C, B, 0);
    SuffixTreeSet S = SuffixTreeSet(&L);
    for( auto i = 0 ; i < C.length() - B - 1 ; i++ ) {
        S.parse(&p, p.next());
        p >> 1;
    }
    if( verbose ) {
        spdlog::info("Timer:: Parsing ms: {:}", timer.toc_ms());
    }

    if( dump ) {

        if( json ) {

            if( verbose ) {
                spdlog::info("Serializing parsed suffix tree to JSON");
            }

            timer.tic();
            auto j = S.json();
            if( verbose ) {
                spdlog::info("Timer:: JSON serialization us: {:}", timer.toc_us());
            }

            ofstream ofs("model.json", ios_base::out);
            ofs << j;
            ofs.close();

        } else {

            if( verbose ) {
                spdlog::info("Serializing parsed data to protobuf");
            }

            timer.tic();
            auto S_proto = S.proto();
            if( verbose ) 
                spdlog::info("Timer:: Protobuf serialization ms: {:}", timer.toc_ms());

            ofstream ofs("model.proto.bin", ios_base::out | ios_base::binary);
            S_proto.SerializeToOstream(&ofs);
            ofs.close();

            efnlp::PROTO_VERSION::SuffixTreeSet ST_proto;

            ifstream in("model.proto.bin", ios::in | ios::binary);
            if( !ST_proto.ParseFromIstream(&in) ) {
                spdlog::info("Failed to deserialize written protobuf data");
            } else {
                timer.tic();
                SuffixTreeSet ST = SuffixTreeSet(&L, &ST_proto);
                if( verbose ) 
                    spdlog::info("Timer:: Deserialized proto ms: {:}", timer.toc_ms());
            }
            in.close();

        }

    }

    if( stats && verbose ) {

        int c;

        spdlog::info("Estimating prefixes...");

        timer.tic();
        c = S.countPrefixes();
        if( verbose ) {
            spdlog::info("Timer:: Prefix count ms: {}", timer.toc_ms());
        }

        spdlog::info("Stats:: Prefix count {} ({:0.2f}%)", c, 100.0f*((double)c)/((double)(N-B-1)));

        spdlog::info("Estimating patterns...");

        timer.tic();
        c = S.countPatterns();
        if( verbose ) {
            spdlog::info("Timer:: Pattern count ms: {}", timer.toc_ms());
        }

        spdlog::info("Stats:: Pattern count {} ({:0.2f}%)", c, 100.0f*((double)c)/((double)(N-B-1)));

    }

    if( memory && verbose ) {

        spdlog::info("Estimating memory...");

        timer.tic();
        auto b = S.bytes();
        if( verbose ) {
            spdlog::info("Timer:: Mem estimate ms: {}", timer.toc_ms());
        }

        spdlog::info("Stats:: Memory {:0.2f}MB ({:}B)", (double)b/1024.0/1024.0, b);
    }

    if( G > 0 ) {

        if( verbose ) {
            spdlog::info("Encoding prompt \"{}\"", textprompt);
        }

        vector<TokenType> encoded = L.encode(textprompt);
        TokenString prompt = TokenString( &encoded );

        if( verbose ) {
            spdlog::info("Generating {} tokens", G);
        }

        timer.tic();
        TokenString gen = S.generate(G, B, &prompt);
        if( verbose ) {
            spdlog::info("Timer:: Generation us/tok: {}", timer.toc_us()/G);
        }

        if( output.length() > 0 ) {

            // TODO: Why is dump writing a binary file?
            // gen.dump(output, &L);

            auto s = gen.str(&L);
            ofstream out(output);
            if( out.is_open() ) {
                out << s; 
                out.close();
            }

        } else {
            cout << "- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - \n";
            cout << gen.str(&L) << "\n";
            cout << "- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - \n";
        }
    }

    if( verbose ) {
        spdlog::info("Finished");
    }

    return 0;
}
