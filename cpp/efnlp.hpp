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

#include "nlohmann/json.hpp"

#include "efnlp.pb.h" // Note: path depends on cmake config

#define PROTO_VERSION v1alpha1

using namespace std; 
using jsonpp = nlohmann::json;

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * 

 Misc

 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

typedef uint8_t ByteType;   // the internal type of a byte for encoding
typedef uint16_t TokenType; // the internal type of a token (16 is plenty)
typedef uint32_t CountType; // the internal type of a "count"
typedef double ProbType; // the internal type of a "probability"

typedef struct _Version{
    int major;
    int minor;
} _Version;

typedef struct _Encoding{
    TokenType token;
    bool valid;
    uint32_t offset;
} _Encoding;

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

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * 

 "Language" modeling; basically tokenization utilities. 

 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

class SuffixEncoder {

protected:
    ByteType value;     // a byte
    uint32_t depth;     // how deep from here the suffix goes
    TokenType token;    // a token
    bool atom;          // whether this element is "set"
    map<ByteType, SuffixEncoder> prefixes;

public:
    SuffixEncoder(ByteType v) : value(v), depth(0), atom(false) {}

    SuffixEncoder(const efnlp::PROTO_VERSION::SuffixEncoder * P) {
        value = (ByteType)P->value();
        depth = P->depth();
        token = (TokenType)P->token();
        atom = P->atom();
        for( auto i = 0 ; i < P->prefixes_size() ; i++ ) {
            auto E = SuffixEncoder(&P->prefixes(i));
            prefixes.emplace(E.getValue(), E);
            // workaround for no default constructor
        }
    }

    efnlp::PROTO_VERSION::SuffixEncoder proto() const {
        efnlp::PROTO_VERSION::SuffixEncoder P;
        P.set_value((uint32_t)value); // smallest avail in proto
        P.set_depth(depth);
        P.set_token((uint32_t)token); // smallest avail in proto
        P.set_atom(atom);
        for( auto [v, E] : prefixes ) {
            auto p = E.proto(); // recursion
            P.add_prefixes()->CopyFrom(p);
        }
        return P;
    }

    SuffixEncoder& operator[](ByteType v) { return prefixes[v]; };

    ByteType getValue() const { return value; }
    uint32_t getDepth() const { return depth; }
    TokenType getToken() const { return token; }
    bool isAtom() const { return atom; }

    map<TokenType, vector<ByteType>> getDecoder() const {
        map<TokenType, vector<ByteType>> D;
        if( atom ) {
            D[token] = vector<ByteType>{value};
        }
        for( auto const& [V, E] : prefixes ) { // ByteType, SuffixEncoder
            for( auto [t, s] : E.getDecoder() ) { // TokenType, vector<ByteType>
                s.push_back(value);
                D[t] = s;
            }
        }
        return D;
    }

    // jsonpp json() const {
    //     // merge all jsons from prefixes, then maybe add
    //     // jsonpp j;
    //     // jsonpp k = 
    //     // j["lang"] = jsonpp(stot);
    //     // return j;
    // }

    uint32_t define(const uint8_t * p, uint8_t * q, const TokenType t) {
        if( q == p ) {
            token = t;
            atom = true; // declare this encoder "defined"
            return 0;
        }
        uint8_t * r = q-1; // q > p => r >= p
        uint8_t b = *r;
        if( prefixes.count(b) == 0 ) {
            prefixes[b] = SuffixEncoder(b);
        }
        auto d = prefixes[b].define(p, r, t);
        if( d > depth ) {
            depth = d;
        }
        return depth;
    }

    _Encoding encode(const uint8_t * p, const uint8_t * q) {
        if( q == p ) {
            return _Encoding{token, atom, 1};
        }
        auto r = q-1; // q > p => r >= p
        auto b = *r;
        if( prefixes.count(b) == 0 ) {
            return _Encoding{token, atom, 1};
        }
        auto e = prefixes[b].encode(q, r); // access rules out const func
        if( e.valid ) {
            return _Encoding{e.token, e.valid, e.offset+1};
        }
        return _Encoding{token, atom, 1};
    }

};


class Language {

protected:
    string name;
    // TODO: version
    uint32_t size;
    uint32_t depth;
    map<ByteType, SuffixEncoder> suffixes;
    map<TokenType, string> decoder;

public:

    Language(efnlp::PROTO_VERSION::Language * P) {
        name = P->name();
        size = P->stats().size();
        depth = P->stats().depth();
        map<TokenType, vector<ByteType>> _decoder;
        for( auto i = 0 ; i < P->suffixes_size() ; i++ ) {
            auto E = SuffixEncoder(&P->suffixes(i));
            suffixes.emplace(E.getValue(), E);
            // workaround for no default constructor
            for( auto const& [t, v] : E.getDecoder() ) { // TokenType, vector<ByteType>
                if( _decoder.count(t) > 0 ) {
                    throw invalid_argument(
                        ErrFmt() << "Token " << t << " appears to repeat"
                    );
                }
                _decoder[t] = v;
            }
        }
        // define decoder by mapping the vectors to strings
        // the successive bytes _should_ form unicode
        for( auto const& [t, v] : _decoder ) {
            decoder[t] = ""; // TODO: convert vector<uint8_t> to unicode string
        }
    }

    efnlp::PROTO_VERSION::Language proto() const {
        // TODO: version
        // TODO: options
        efnlp::PROTO_VERSION::Language P;
        P.set_name(name);
        P.mutable_stats()->set_size(size);
        P.mutable_stats()->set_depth(depth);
        for( auto const& [b, E] : suffixes ) {
            auto p = E.proto(); // recursion
            P.add_suffixes()->CopyFrom(p);
        }
        return P;
    }

    int getSize() const { return size; }
    int getDepth() const { return depth; }

    void print() const {
        for( auto const& [t, s]: decoder ) {
            cout << "(" << t << "," << s << ")\n";
        }
    }

    jsonpp json() const {
        jsonpp j;
        for( auto const& [t, s]: decoder ) {
            j[s] = t;
        }
        return j;
    }

    // // encode/decode with [] operator
    // TokenType& operator[](T c) { return stot[c]; };
    // T& operator[](TokenType c) { return ttos[c]; };

    // // explicit encode/decode for single instances
    // TokenType encode(T c) { return stot[c]; };
    // T decode(TokenType t) { return ttos[t]; };

    // bulk encode/decode
    vector<TokenType> encode(string in) {
        vector<T> out;
        out.reserve(in.size());
        for( auto t: in )
            out.push_back(stot[t]);
        return out;
    }

    string decode(vector<TokenType> in) {
        vector<char> out;
        out.reserve(in.size());
        for( auto const& t: in ) {
            if( decoder.count(t) == 0 ) {
                throw invalid_argument(
                    ErrFmt() << "Token " << t << " is not decodable"
                );
            }
            out.push_back(decoder[t]);
        }
        return out;
    }

};


template <typename T> class LanguageV0 {

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

typedef LanguageV0<char> _CL;

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

class Sampler {

    CountType total;
    map<TokenType, CountType> counts;

    // ProbType total;
    // vector<ProbType> counts;
    // map<TokenType, int> locs;
    // map<int, TokenType> toks;

public: 
    Sampler() : total(0) {};
    Sampler(const efnlp::PROTO_VERSION::Sampler * S) {
        total = S->total();
        CountType totalCheck = 0;
        for( auto i = 0 ; i < S->counts_size() ; i++ ) {
            auto d = S->counts(i); // a SamplerTokenCount (or pointer to?)
            counts[d.token()] = d.count();
            totalCheck += d.count();
        }

        if( totalCheck != total ) {
            // throw? 
            cout << "Error!!!! totals mismatch: " << total << " vs " << totalCheck;
        }
    }
    ~Sampler() {};

    void print() {
        cout << total << ", ";
        for( auto const& [t, c] : counts )
            cout << t << "(" << c << "), ";
    }
    
    template<typename T> void render(Language<T> * L) {
        cout << total << ", ";
        for( auto const& [t, c] : counts )
            cout << '"' << (*L)[t] << '"' << "(" << c << "), ";
    }

    int size() { return counts.size(); }

    jsonpp json() {
        jsonpp j;
        j["total"] = total;
        vector<jsonpp> tmp;
        tmp.reserve(counts.size());
        for( auto const& [t, c] : counts ) {
            jsonpp k;
            k["token"] = t;
            k["count"] = c;
            tmp.push_back(k);
        }
        j["data"] = jsonpp(tmp);
        return j;
    }

    efnlp::PROTO_VERSION::Sampler proto() {
        efnlp::PROTO_VERSION::Sampler s;
        s.set_total(total);
        for( auto const& [t, c] : counts ) {
            auto d = s.add_counts();
            d->set_token(t);
            d->set_count(c);
        }
        return s;
    }

    size_t bytes() {
        return sizeof(CountType) + counts.size() * (sizeof(TokenType)+sizeof(CountType));
    }

    void add(TokenType t) {
        total += 1;
        if( counts.count(t) == 0 )
            counts[t] = 1;
        else
            counts[t] += 1;
    }

    CountType getTotal() {
        return total;
    }

    TokenType sample() {
        auto r = double(total) * rand() / (RAND_MAX);
        for( auto const& [t, c] : counts ) {
            if( r < (double)c )
                return t;
            r -= (double)c;
        }
        return 0; // THIS SHOULD NOT BE REACHABLE; throw?
    }

    CountType getCount(TokenType t) {
        if( counts.count(t) == 0 ) 
            return 0;
        return counts[t];
    }

    map<TokenType, CountType> getCounts() {
        return counts; // TODO: reference?
    }

    ProbType probability(TokenType t) {
        if( counts.count(t) == 0 ) 
            return 0.0f;
        return ((double)counts[t])/((double)total);
    }

    map<TokenType, ProbType> histogram() {
        map<TokenType, ProbType> D;
        for( auto const& [t, c] : counts )
            D[t] = probability(t);
        return D;
    }

    void merge(Sampler * S) {
        total += S->getTotal();
        for( auto const& [t, c] : counts ) {
            if( S->getCount(t) > 0 ) 
                counts[t] += S->getCount(t);
        }
        for( auto const& [t, c] : S->getCounts() ) {
            if( counts.count(t) == 0 )
                counts[t] = c;
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
