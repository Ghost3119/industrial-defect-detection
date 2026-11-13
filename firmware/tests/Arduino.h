#pragma once
// Doble de Arduino para ejecutar el sketch real sin placa, USB ni motor.
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <deque>
#include <map>
#include <string>
#include <vector>
using std::min;
using std::max;
constexpr int LOW = 0, HIGH = 1, OUTPUT = 1;
inline uint64_t clockUs = 0;
inline std::map<int, int> pins, pwm, frequencies, pinModes;
inline unsigned long millis() { return static_cast<uint32_t>(clockUs / 1000); }
inline unsigned long micros() { return static_cast<uint32_t>(clockUs); }
inline void pinMode(int pin, int mode) { pinModes[pin] = mode; }
inline void digitalWrite(int pin, int value) { pins[pin] = value; }
inline void analogWrite(int pin, int value) { pwm[pin] = value; }
inline void tone(int pin, unsigned long hz) { frequencies[pin] = static_cast<int>(hz); }
inline void noTone(int pin) { frequencies[pin] = 0; }

class String {
  std::string value;
public:
  String(const char* text = "") : value(text) {}
  explicit String(std::string text) : value(std::move(text)) {}
  void trim() {
    auto begin = value.find_first_not_of(" \t\r\n");
    value = begin == std::string::npos ? "" : value.substr(begin, value.find_last_not_of(" \t\r\n") - begin + 1);
  }
  void toUpperCase() { for (char& c : value) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c))); }
  bool operator==(const char* text) const { return value == text; }
  bool startsWith(const char* text) const { return value.rfind(text, 0) == 0; }
  String substring(unsigned int offset) const { return String(value.substr(offset)); }
  unsigned int length() const { return static_cast<unsigned int>(value.size()); }
  char operator[](unsigned int index) const { return value[index]; }
  String& operator+=(char c) { value += c; return *this; }
};
struct FakeSerial {
  std::deque<char> input;
  std::vector<std::string> output;
  void begin(int baud) { if (baud != 115200) throw "Unexpected baud rate"; }
  int available() { return static_cast<int>(input.size()); }
  char read() { char c = input.front(); input.pop_front(); return c; }
  void println(const char* text) { output.emplace_back(text); }
  void inject(const std::string& text) { for (char c : text) input.push_back(c); }
};
inline FakeSerial Serial;
class Servo {
public:
  int pulse = 0;
  void attach(int, int, int) {}
  void writeMicroseconds(int us) { pulse = us; }
};
