// PC 회귀시험 전용 대역. AVR 전기 특성/인터럽트 타이밍을 재현하지 않습니다.
#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <sstream>
#include <string>
using std::max;
constexpr int HIGH=1, LOW=0, OUTPUT=1, INPUT_PULLUP=2, RISING=3, A8=62;
constexpr int COM1A1=7, COM1A0=6, COM1B1=5, COM1B0=4, WGM11=1;
constexpr int COM5B1=5, COM5B0=4, COM5C1=3, COM5C0=2, WGM51=1;
constexpr int WGM13=4, WGM12=3, CS10=0, WGM53=4, WGM52=3, CS50=0;
constexpr int PK0=0, PCINT16=0, PCIF2=2, PCIE2=2;
#define _BV(x) (1U << (x))
#define ISR(vector) void vector()
inline uint8_t TCCR1A=0, TCCR1B=0, TCCR5A=0, TCCR5B=0;
inline uint8_t PINK=0, PCMSK2=0, PCIFR=0, PCICR=0;
inline uint16_t OCR1A=0, OCR1B=0, OCR5B=0, OCR5C=0, ICR1=0, ICR5=0;
inline uint32_t fakeMillis=0;
inline int pins[80]={};
inline uint32_t millis() { return fakeMillis; }
inline void digitalWrite(int pin,int value) { pins[pin]=value; }
inline void pinMode(int,int) {}
inline int digitalPinToInterrupt(int pin) { return pin; }
inline void attachInterrupt(int,void(*)(),int) {}
class String {
    std::string value;
public:
    String(const char* text): value(text) {}
    bool startsWith(const char* prefix) const { return value.rfind(prefix,0)==0; }
    bool operator==(const char* text) const { return value==text; }
    const char* c_str() const { return value.c_str(); }
    size_t length() const { return value.length(); }
    void trim() {
        auto first=value.find_first_not_of(" \t\r\n");
        if(first==std::string::npos) { value.clear(); return; }
        value=value.substr(first,value.find_last_not_of(" \t\r\n")-first+1);
    }
};
class FakeSerial {
public:
    std::deque<char> input;
    std::string output;
    void begin(int) {}
    int available() { return static_cast<int>(input.size()); }
    int read() { char c=input.front(); input.pop_front(); return c; }
    template<class T> void print(T value) { std::ostringstream s; s<<value; output+=s.str(); }
    void print(uint8_t value) { print(static_cast<unsigned>(value)); }
    void print(const String& value) { output+=value.c_str(); }
    void println() { output+='\n'; }
    template<class T> void println(T value) { print(value); println(); }
};
inline FakeSerial Serial;
