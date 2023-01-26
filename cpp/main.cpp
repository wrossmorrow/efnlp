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
#include "nlohmann/json.hpp"

#include "efnlp.pb.h" // Note: path depends on cmake config

#define PROTO_VERSION v1alpha1

using namespace std; 
using jsonpp = nlohmann::json;

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * 

 Misc

 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

typedef uint32_t TokenType; // the internal type of a token

typedef std::chrono::high_resolution_clock Clock;

size_t fileSize(ifstream * in) {
    if( in->is_open() ) {
        auto pos = in->tellg();
        in->seekg(0, std::ios::end);
        auto len = in->tellg();
        in->seekg(pos);
        return len;
    }
    return 0;
}

class ErrFmt {
    stringstream stream_;

    ErrFmt(const ErrFmt &);
    ErrFmt & operator = (ErrFmt &);

public:
    ErrFmt() {}
    ~ErrFmt() {}

    template <typename Type> ErrFmt & operator << (const Type & value) {
        stream_ << value;
        return *this;
    }

    string str() const { return stream_.str(); }
    operator std::string () const { return stream_.str(); }

    enum ConvertToString {
        to_str
    };
    string operator >> (ConvertToString) { return stream_.str(); }

};

class Timer {
    chrono::time_point<chrono::steady_clock> s;

public:
    void tic() { s = Clock::now(); }

    double toc_s() {
        auto e = Clock::now();
        return chrono::duration_cast<std::chrono::seconds>(e -s).count();
    }

    double toc_ms() {
        auto e = Clock::now();
        return chrono::duration_cast<std::chrono::milliseconds>(e -s).count();
    }

    double toc_us() {
        auto e = Clock::now();
        return chrono::duration_cast<std::chrono::microseconds>(e -s).count();
    }

    double toc_ns() {
        auto e = Clock::now();
        return chrono::duration_cast<std::chrono::nanoseconds>(e -s).count();
    }
};

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * 

 "Language" modeling; basically tokenization utilities. 

 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

template <typename T> class Language {

protected:
    int size;
    map<TokenType, T> ttos;
    map<T, TokenType> stot;

public:

    int length() { return size; }

    void print() {
        for( auto const& [t, s]: ttos )
            cout << "(" << t << "," << s << ")\n";
    }

    jsonpp json() {
        jsonpp j;
        j["lang"] = jsonpp(stot);
        return j;
    }

    // efnlp::PROTO_VERSION::Language proto() {
    //     efnlp::PROTO_VERSION::Language lang;
    //     lang.set_name("CharLanguage");
    //     for( auto const& [t, c] : ttos ) {
    //         auto enc = lang.add_lang();
    //         enc->set_token(t);
    //         enc->set_data(&c); // TODO: ok for "bytes" type?
    //     }
    //     return lang;
    // }

    // encode/decode with [] operator
    TokenType& operator[](T c) { return stot[c]; };
    T& operator[](TokenType c) { return ttos[c]; };

    // explicit encode/decode for single instances
    TokenType encode(T c) { return stot[c]; };
    T decode(TokenType t) { return ttos[t]; };

    // bulk encode/decode
    vector<TokenType> encode(vector<T> in) {
        vector<T> out;
        out.reserve(in.size());
        for( auto t: in )
            out.push_back(stot[t]);
        return out;
    }

    vector<T> decode(vector<TokenType> in) {
        vector<T> out;
        out.reserve(in.size());
        for( auto t: in )
            out.push_back(ttos[t]);
        return out;
    }

};

typedef Language<char> _CL;

class CharLanguage: public _CL {

public:

    CharLanguage(const string text) {

        map<char, int> lang;

        size = text.length();

        // set<char> lang(begin(text), end(text));?

        for( auto i = 0 ; i < size ; i++ ) {
            auto c = text[i];
            if( lang.count(c) == 0 ) { lang[c] = 1; }
            else { lang[c]++; }
        }

        // lang has unique chars and their counts

        vector<char> values;
        values.reserve(lang.size());
        for( auto const& [c, n] : lang )
            values.push_back(c);

        // not needed with map read?
        // sort(values.begin(), values.end());

        // construct encoder/decoder maps
        int i = 0;
        for( auto const& v : values ) {
            stot[v] = i; ttos[i] = v; i++;
        }

    }

    CharLanguage(const char * filename) {
        ifstream in(filename, ios::in);
        _read(&in);
    }

    CharLanguage(ifstream * in) { _read(in); }

    CharLanguage(const efnlp::PROTO_VERSION::Language * L) {
        // templating: 
        // 
        //     map<TokenType, char> ttos;
        //     map<char, TokenType> stot;
        // 
        size = L->lang_size();
        for( auto i = 0 ; i < L->lang_size() ; i++ ) {
            auto enc = L->lang(i);
            TokenType t = enc.token(); // uint32
            char v = enc.data()[0]; // TODO: can't be "stable"?
            stot[v] = t;
            ttos[t] = v;
        }
    }

    ~CharLanguage() {} // do we need to delete maps? or handled... 

    jsonpp json() {
        jsonpp j;
        vector<jsonpp> tmp;
        tmp.reserve(stot.size());
        for( auto const& [c, t] : stot ) {
            cout << "  " << c << " : " << t << "\n";
            jsonpp k;
            k["data"] = c;
            k["token"] = t;
            tmp.push_back(k);
        }
        j["lang"] = jsonpp(tmp);
        return j;
    }

    efnlp::PROTO_VERSION::Language proto() {
        // templating: 
        // 
        //     map<TokenType, char> ttos;
        //     map<char, TokenType> stot;
        // 
        efnlp::PROTO_VERSION::Language lang;
        lang.set_name("CharLanguage");
        for( auto const& [t, c] : ttos ) { // t: TokenType(uint32), c: char
            auto enc = lang.add_lang();
            enc->set_token(t);
            enc->set_data(&c, 1); // add size, need char to be set as a const char * (array)
        }
        return lang;
    }

    // C++ does not resolve overloaded methods with inheritance; if we
    // define a "string" method, we have to re-define here. 
    TokenType encode(char c) { return _CL::encode(c); };
    char decode(TokenType t) { return _CL::decode(t); };

    vector<TokenType> encode(ifstream * in) {
        vector<TokenType> Ts;
        if( in->is_open() ) {
            Ts.reserve(fileSize(in));
            in->seekg(0, ios::beg);
            while(*in)
                Ts.push_back(_CL::encode(in->get()));
        }
        return Ts;
    }
    
    vector<TokenType> encode(string s) {
        vector<TokenType> Ts;
        Ts.reserve(s.length());
        for( auto &c : s ) { Ts.push_back(stot[c]); }
        return Ts;
    }
    
    string decode(vector<TokenType> Ts) { 
        stringstream ss;
        for( auto t : Ts ) { ss << ttos[t]; }
        return ss.str();
    }

private:
    void _read(ifstream * in) {
        map<char, int> lang;
        vector<char> values;

        if( in->is_open() ) {
            in->seekg(0, ios::beg);
            while( *in ) {
                auto c = in->get();
                if( lang.count(c) == 0 ) {
                    lang[c] = 1;
                } else {
                    lang[c]++;
                }
            }
            in->clear();
        }

        // lang has unique chars and their counts
        values.reserve(lang.size());
        for( auto const& cs: lang ) {
            values.push_back(cs.first);
        }

        // not needed with map read?
        sort(values.begin(), values.end());

        // construct encoder/decoder maps
        int i = 0;
        for( auto v: values ) {
            stot[v] = i;
            ttos[i] = v;
            i++;
        }
    }
};

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * 

 Token-string/prefix datastructures

 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

class TokenString {
    int N;
    TokenType * d;

public:

    TokenString(int s) : N(s) { d = new TokenType[s]; };

    TokenString(vector<TokenType> * Ts) {
        N = Ts->size();
        d = new TokenType[N]; 
        copy(Ts->begin(), Ts->end(), d);
    }

    template<typename T> TokenString(ifstream * in, Language<T> * L) { 
        if( in->is_open() ) {
            N = fileSize(in);
            d = new TokenType[N];
            in->seekg(0, ios::beg);
            int i = 0;
            while(*in) {
                d[i++] = (*L)[in->get()];
            }
        }
    }

    template<typename T> TokenString(string text, Language<T> * L) { 
        N = text.length(); // TODO: this presumes CharLanguage...
        d = new TokenType[N];
        for( auto i = 0 ; i < N ; i++ ) {
            d[i] = (*L)[text[i]];
        }
    }

    TokenString(TokenString&& T) : N(T.N), d(T.d) { T.d = nullptr; }; // move
    ~TokenString() { delete d; }; // free alloc'd mem

    void print() {
        for( auto i = 0 ; i < N ; i++ ) { cout << d[i] << ","; }
    }

    template<typename T> void render(Language<T> * L) {
        for( auto i = 0 ; i < N ; i++ ) { cout << (*L)[d[i]]; }
    }

    template<typename T> void dump(string filename, Language<T> * L) {
        ofstream out(filename);
        if( out.is_open() ) {
            for( auto i = 0 ; i < N ; i++ ) { 
                out << (*L)[d[i]];
            }
            out.close();
        }
    }

    template<typename T> string str(Language<T> * L) {
        stringstream ss;
        for( auto i = 0 ; i < N ; i++ ) { ss << (*L)[d[i]]; }
        return ss.str();
    }

    int length() { return N; }

    TokenType& operator[](int i) { 
        if( i >= N ) { 
            throw invalid_argument(
                ErrFmt() << "Index " << i << " out of bounds for " << N
            ); 
        }
        return d[i]; 
    };
};


class Prefix {
    int N, s, e;
    TokenString * d;

public:
    Prefix(TokenString * d, int N, int s) : N(N), s(s), d(d) { // NOTE: ordering avoids warning
        e = s + N; // e >= s
        if( e >= d->length() ) {
            throw invalid_argument("Window too large for data");
        }
    };
    ~Prefix() {};

    void print() {
        for( auto i = 0 ; i < N ; i++ ) { cout << (*d)[s+i] << ","; }
        cout << " | " << next();
    }

    template<typename T> void render(Language<T> * L) {
        for( auto i = 0 ; i < N ; i++ ) { cout << '"' << (*L)[(*d)[s+i]] << '"'; }
        cout << " | " << (*L)[next()];
    }

    int length() { return N; }
    TokenType first() { return (*d)[s]; }
    TokenType last() { return (*d)[e-1]; }
    TokenType next() {
        if( e < d->length() - 1 ) { return (*d)[e]; }
        return 0; // TODO: throw unfortunately
    }

    Prefix pop() { return prefix(N-1); } // p[:-1]; convenience for a prefix without last element
    Prefix push() { return suffix(N-1); } // p[1:]; convenience for a prefix without first element

    Prefix prefix(int M) {
        // first M elements of this prefix
        // if( M <= 0 ) { throw invalid_argument("Window size must be positive"); }
        if( M > N ) { throw invalid_argument("Window too large for prefix"); }
        if( M == N ) { return *this; }
        return Prefix(d, M, s);
    }
    Prefix suffix(int M) { 
        // last M elements of this prefix
        // if( M <= 0 ) { throw invalid_argument("Window size must be positive"); }
        if( M < N ) { throw invalid_argument("Window too large for suffix"); }
        if( M == N ) { return *this; }
        return Prefix(d, M, e-M);
    }

    TokenType& operator[](int i) {
        if( i >= N || i < s - e ) {
            throw invalid_argument(
                ErrFmt() << "Index " << i << " out of bounds for [" << s << "," << e << ")"
            ); 
        }
        if( i < 0 ) {
            return (*d)[e+i]; 
        }
        return (*d)[s+i];
    }

    void operator<<(int i) {
        s -= i; e -= i;
        if( s < 0 || e >= d->length() ) {
            s += i; e += i;
            throw invalid_argument("Shift takes window out of bounds");
        }
    }

    void operator>>(int i) {
        s += i; e += i;
        if( s < 0 || e >= d->length() ) {
            s -= i; e -= i;
            throw invalid_argument("Shift takes window out of bounds");
        }
    }
};


class Pattern {
    Prefix * p;
    TokenType s;
public:
    Pattern(Prefix * p, TokenType s) : p(p), s(s) {};
    ~Pattern() {};

    Prefix * prefix() { return p; }
    TokenType successor() { return s; }
};

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * 

 Sampling

 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

typedef double ProbType;

const size_t BYTES_PER_TARGET = sizeof(ProbType) + 2 * sizeof(int) + 2 * sizeof(TokenType);


class Sampler {
    ProbType total;
    vector<ProbType> counts;
    map<TokenType, int> locs;
    map<int, TokenType> toks;

public: 
    Sampler() : total(0) {};
    Sampler(const efnlp::PROTO_VERSION::Sampler * S) {
        total = 1.0f; // TODO: abstracted type safe?
        counts.reserve(S->data_size());
        for( auto i = 0 ; i < S->data_size() ; i++ ) {
            auto d = S->data(i);
            auto t = d.token();
            locs[t] = i;
            toks[i] = t;
            counts.push_back(d.prob());
        }
    }
    ~Sampler() {};

    void print() {
        for( auto const& [t, i] : locs )
            cout << t << "(" << counts[i]/total << "), ";
    }
    
    template<typename T> void render(Language<T> * L) {
        for( auto const& [t, i] : locs )
            cout << '"' << (*L)[t] << '"' << "(" << counts[i]/total << "), ";
    }

    int size() { return counts.size(); }

    jsonpp json() {
        jsonpp j;
        j["total"] = total;
        vector<jsonpp> tmp;
        tmp.reserve(counts.size());
        for( auto const& [t, i] : locs ) {
            jsonpp k;
            k["token"] = t;
            k["count"] = counts[i];
            tmp.push_back(k);
        }
        j["data"] = jsonpp(tmp);
        return j;
    }

    efnlp::PROTO_VERSION::Sampler proto() {
        efnlp::PROTO_VERSION::Sampler s;
        for( auto const& [t, i] : locs ) {
            auto d = s.add_data();
            d->set_token(t);
            d->set_prob(counts[i]/total);
        }
        return s;
    }

    size_t bytes() {
        return BYTES_PER_TARGET * counts.size() + sizeof(ProbType);
    }

    void add(TokenType t) {
        total += 1.0f;
        if( locs.count(t) == 0 ) {
            auto i = counts.size();
            counts.push_back(1.0f);
            locs[t] = i;
            toks[i] = t;
        } else {
            counts[locs[t]] += 1.0f;
        }
    }

    TokenType sample() {
        auto r = total * rand() / (RAND_MAX);
        for( auto i = 0ul ; i < counts.size() ; i++ ) {
            if( r < counts[i] ) { return toks[i]; }
            r -= counts[i];
        }
        return 0; // THIS SHOULD NOT BE REACHABLE
    }

    ProbType probability(TokenType t) {
        if( locs.count(t) == 0 ) 
            return 0.0f;
        return counts[locs[t]]/total;
    }

    map<TokenType, ProbType> histogram() {
        map<TokenType, ProbType> D;
        for( auto [t, i] : locs )
            D[t] = counts[i];
        return D;
    }

    void merge(Sampler * S) {
        auto D = S->histogram();
        for( auto [t, c] : D ) {
            total += c;
            if( locs.count(t) == 0 ) {
                auto i = counts.size();
                counts.push_back(c);
                locs[t] = i;
                toks[i] = t;
            } else {
                counts[locs[t]] += c;
            }
        }
    }

    void operator+(TokenType t) { add(t); }

};

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * 

 Suffix trees

 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

class SuffixTree {
    int token;
    map<TokenType, SuffixTree> prefixes;
    Sampler sampler;

public:
    SuffixTree(const TokenType t) : token(t) { sampler = Sampler(); };
    SuffixTree(const efnlp::PROTO_VERSION::SuffixTree * P) {
        token = P->token();
        sampler = Sampler(&P->sampler());
        for( auto i = 0 ; i < P->prefixes_size() ; i++ ) {
            auto SC = SuffixTree(&P->prefixes(i));
            prefixes.emplace(SC.getToken(), SC);
        }
    }
    ~SuffixTree() {};

    void print(string h) {
        cout << h << "SuffixTree(" << token << "): ";
        sampler.print(); cout << "\n";
        for( auto [t, c] : prefixes )
            c.print(h + "  ");
    }

    template<typename T> void render(Language<T> * L, string h) {
        cout << h << "SuffixTree(\"" << (*L)[token] << "\"): ";
        sampler.render(L); cout << "\n";
        for( auto [t, c] : prefixes )
            c.render(L, h + "  ");
    }

    jsonpp json() {
        jsonpp j;
        j["token"] = token;
        j["sampler"] = sampler.json();
        map<TokenType, jsonpp> tmp;
        for( auto [t, c] : prefixes ) 
            tmp[t] = c.json();
        j["prefixes"] = jsonpp(tmp);
        return j;
    }

    efnlp::PROTO_VERSION::SuffixTree proto() {
        efnlp::PROTO_VERSION::SuffixTree st;
        st.set_token(token);
        auto smpl = sampler.proto();
        st.mutable_sampler()->CopyFrom(smpl);
        for( auto [t, tree] : prefixes ) {
            auto _st = tree.proto(); // recursion
            st.add_prefixes()->CopyFrom(_st);
        }
        return st;
    }

    TokenType getToken() { return token; }

    void parse(Prefix p, const TokenType s) {
        sampler + s;
        if( p.length() > 0 ) {
            auto t = p[-1];
            if( prefixes.count(t) == 0 )
                prefixes.emplace(t, SuffixTree(t));
            prefixes.at(t).parse(p.pop(), s);
        }
    }

    size_t bytes() { // return estimate for memory used
        auto b = sampler.bytes();
        for( auto [t, c] : prefixes ) 
            b += c.bytes();
        return b;
    }

    int countPrefixes() {
        if( prefixes.size() == 0 )
            return 1;

        int C = 0;
        for( auto [c, st] : prefixes )
            C += st.countPrefixes();
        return C;
    }

    int countPatterns() {
        if( prefixes.size() == 0 )
            return sampler.size();

        int C = 0;
        for( auto [c, st] : prefixes )
            C += st.countPatterns();
        return C;
    }

    // vector<TokenString> prefixes();
    // {
    //     vector<TokenString> Ts;
    //     if( prefixes.size() == 0 ) {
    //         vector<TokenType> T = vector<TokenType> { token };
    //         TokenString TS = TokenString(&T);
    //         Ts.push_back(TS);
    //     } else {

    //     }
    //     return Ts;
    // }

    vector<Pattern> patterns();

    Prefix * search(Prefix p);
    bool match(Prefix);

    TokenType sample(Prefix p) {
        if( p.length() == 0 )
            return sampler.sample();

        auto s = p[-1];
        if( prefixes.count(s) == 0 )
            return sampler.sample();
        return prefixes.at(s).sample(p.pop());
    }

};


class SuffixTreeSet {
    int N;
    map<TokenType, SuffixTree> prefixes;

public:
    SuffixTreeSet(int N) : N(N) {};
    template<typename T> SuffixTreeSet(Language<T> * L) { N = L->length(); }
    template<typename T> SuffixTreeSet(
        Language<T> * L, const efnlp::PROTO_VERSION::SuffixTreeSet * S
    ) { 
        N = L->length();
        for( auto i = 0 ; i < S->prefixes_size() ; i++ ) {
            auto SC = SuffixTree(&S->prefixes(i));
            prefixes.emplace(SC.getToken(), SC);
        }
    }
    ~SuffixTreeSet() {};

    void print() {
        for( auto [t, tree] : prefixes ) { 
            tree.print(""); cout << "\n";
        }
    }

    template<typename T> void render(Language<T> * L) {
        for( auto [t, tree] : prefixes ) { 
            tree.render(L, ""); cout << "\n";
        }
    }

    jsonpp json() {
        jsonpp j;
        for( auto [t, tree] : prefixes ) 
            j["prefixes"][t] = tree.json();
        return j;
    }

    efnlp::PROTO_VERSION::SuffixTreeSet proto() {
        efnlp::PROTO_VERSION::SuffixTreeSet sts;
        for( auto [t, tree] : prefixes ) {
            auto st = tree.proto();
            sts.add_prefixes()->CopyFrom(st);
        }
        return sts;
    }

    void parse(Prefix * p, TokenType s) { // why not Pattern?
        if( p->length() == 0 ) {
            throw invalid_argument("Cannot parse an empty prefix");
        }
        auto t = (*p)[-1];
        if( prefixes.count(t) == 0 )
            prefixes.emplace(t, SuffixTree(t));
        prefixes.at(t).parse(p->pop(), s);
    }

    // from files? (maybe name better)
    void parse(string);
    void parse(const char *);
    void parse(ifstream);

    int bytes() { // return estimate for memory used
        int s = 0;
        for( auto [t, tree] : prefixes )
            s += tree.bytes();
        return s;
    }

    int countPrefixes(TokenType t) { return prefixes.at(t).countPrefixes(); }
    int countPrefixes() {
        int C = 0;
        for( auto [t, tree] : prefixes )
            C += tree.countPrefixes();
        return C;
    }

    int countPatterns(TokenType t) { return prefixes.at(t).countPatterns(); }
    int countPatterns() {
        int C = 0;
        for( auto [t, tree] : prefixes )
            C += tree.countPatterns();
        return C;
    }

    // vector<TokenString> prefixes(TokenType t) { return prefixes.at(t).prefixes(); }
    // vector<TokenString> prefixes(); 
    // {
    //     vector<TokenString> ps;
    //     for( auto [t, tree] : prefixes ) {
    //         auto qs = tree.prefixes();
    //         ps.reserve(ps.size() + qs.size());
    //         ps.insert(ps.end(), qs.begin(), qs.end());
    //     }
    //     return ps;
    // }

    vector<Pattern> patterns(TokenType t) { return prefixes.at(t).patterns(); }
    vector<Pattern> patterns();

    Prefix * search(Prefix * p) { return prefixes.at((*p)[-1]).search(p->pop()); }
    bool match(Prefix * p) { return prefixes.at((*p)[-1]).match(p->pop()); }

    TokenType sample(Prefix * p) { return prefixes.at((*p)[-1]).sample(p->pop()); }

    TokenString generate(int N, int B, TokenString * prompt) {

        auto P = prompt->length();
        if( P == 0 ) { throw invalid_argument("generation requires a prompt"); }

        TokenString gen = TokenString(N+P);

        auto i = 0;

        // copy in the first P tokens
        for( ; i < P ; i++ )
            gen[i] = (*prompt)[i];

        // i == P, but P < B: sample with special prefixes
        // (if we define and shift, we'll get bad accesses)
        for( ; i < B ; i++ ) {
            Prefix q = Prefix(&gen, i, 0);
            gen[i] = sample(&q);
        }

        // now i == B; we can use a full-width prefix and shift
        Prefix p = Prefix(&gen, B, (P >= B ? P-B : 0)); // size longer ok?
        for( ; i < N+P-1 ; i++ ) { 
            gen[i] = sample(&p); 
            p >> 1;
        }

        return gen;
    }

    SuffixTree& operator[](TokenType t) { return prefixes.at(t); };
};

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * 

 main stuff

 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

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

    if( verbose ) 
        spdlog::info("Reading input file");

    timer.tic();
    string text = readFile(filename);
    if( verbose ) 
        spdlog::info("Timer:: Reading text us: {}", timer.toc_us());

    if( verbose ) 
        if( stats )
            spdlog::info(
                "File is {} chars long ({:0.2f}MB)", 
                text.length(), 4.0f*text.length()/1024.0f/1024.0f
            );

        spdlog::info("Parsing language");

    timer.tic();
    CharLanguage L(text);
    if( verbose ) 
        spdlog::info("Timer:: Language parsing ms: {}", timer.toc_ms());

    if( dump ) {

        if( json ) {

            if( verbose )
                spdlog::info("Serializing parsed language to JSON");

            timer.tic();
            auto j = L.json();
            if( verbose ) 
                spdlog::info("Timer:: JSON serialization us: {:}", timer.toc_us());

            ofstream ofs("language.json", ios_base::out);
            ofs << j;
            ofs.close();

        } else {

            if( verbose )
                spdlog::info("Serializing parsed language to protobuf");

            timer.tic();
            auto L_proto = L.proto();
            if( verbose ) 
                spdlog::info("Timer:: Protobuf serialization us: {:}", timer.toc_us());

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

    if( verbose )
        spdlog::info("Encoding corpus");

    timer.tic();
    TokenString C = TokenString(text, &L);
    if( verbose ) 
        spdlog::info("Timer:: Encoding ms: {}", timer.toc_ms());

    N = C.length();

    if( verbose ) 
        if( stats )
            spdlog::info("Stats:: Corpus is {} tokens long", N);
        spdlog::info("Parsing suffix tree");

    timer.tic();
    Prefix p = Prefix(&C, B, 0);
    SuffixTreeSet S = SuffixTreeSet(&L);
    for( auto i = 0 ; i < C.length() - B - 1 ; i++ ) {
        S.parse(&p, p.next());
        p >> 1;
    }
    if( verbose ) 
        spdlog::info("Timer:: Parsing ms: {:}", timer.toc_ms());

    if( dump ) {

        if( json ) {

            if( verbose )
                spdlog::info("Serializing parsed suffix tree to JSON");

            timer.tic();
            auto j = S.json();
            if( verbose ) 
                spdlog::info("Timer:: JSON serialization us: {:}", timer.toc_us());

            ofstream ofs("model.json", ios_base::out);
            ofs << j;
            ofs.close();

        } else {

            if( verbose )
                spdlog::info("Serializing parsed data to protobuf");

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
        if( verbose ) 
            spdlog::info("Timer:: Prefix count ms: {}", timer.toc_ms());

        spdlog::info("Stats:: Prefix count {} ({:0.2f}%)", c, 100.0f*((double)c)/((double)(N-B-1)));

        spdlog::info("Estimating patterns...");

        timer.tic();
        c = S.countPatterns();
        if( verbose ) 
            spdlog::info("Timer:: Pattern count ms: {}", timer.toc_ms());

        spdlog::info("Stats:: Pattern count {} ({:0.2f}%)", c, 100.0f*((double)c)/((double)(N-B-1)));

    }

    if( memory && verbose ) {

        spdlog::info("Estimating memory...");

        timer.tic();
        auto b = S.bytes();
        if( verbose ) 
            spdlog::info("Timer:: Mem estimate ms: {}", timer.toc_ms());

        spdlog::info("Stats:: Memory {:0.2f}MB ({:}B)", (double)b/1024.0/1024.0, b);
    }

    if( G > 0 ) {

        if( verbose ) 
            spdlog::info("Encoding prompt \"{}\"", textprompt);

        vector<TokenType> encoded = L.encode(textprompt);
        TokenString prompt = TokenString( &encoded );

        if( verbose ) 
            spdlog::info("Generating {} tokens", G);

        timer.tic();
        TokenString gen = S.generate(G, B, &prompt);
        if( verbose ) 
            spdlog::info("Timer:: Generation us/tok: {}", timer.toc_us()/G);

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

    if( verbose ) 
        spdlog::info("Finished");

    return 0;
}