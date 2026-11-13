#include "Arduino.h"
#include <cmath>
#include <cstdlib>
#include <iostream>
#include "../conveyor_controller/conveyor_controller.ino"

#define CHECK(expr) do { if (!(expr)) { std::cerr << __LINE__ << ": " << #expr << "\n"; std::exit(1); } } while (0)

void boot(uint64_t atUs = 0) {
  clockUs = atUs;
  running = reverse = alarmOn = discardLine = false;
  targetSpeed = 100;
  currentSpeed = 0;
  lastApplied = -1;
  lastCommand = lastRampMs = 0;
  line = "";
  Serial.input.clear(); Serial.output.clear();
  pins.clear(); pwm.clear(); frequencies.clear(); pinModes.clear();
#if DRIVE_MODE == DRIVE_28BYJ48
  byj48Phase = 0; byj48PhaseValid = false;
#endif
  setup();
}

void send(const std::string& input, const std::string& response) {
  size_t before = Serial.output.size();
  Serial.inject(input);
  do { loop(); } while (Serial.available());
  CHECK(Serial.output.size() == before + 1);
  CHECK(Serial.output.back() == response);
}

void advance(unsigned long ms, bool heartbeat = false) {
  for (unsigned long i = 0; i < ms; ++i) {
    clockUs += 1000; loop();
    if (heartbeat && i % 500 == 0) send("PING\n", "OK PING");
  }
}

void checkStoppedOutput() {
  CHECK(!running);
#if DRIVE_MODE == DRIVE_RELAY
  CHECK(pins[RELAY_PIN] == (RELAY_ACTIVE_LOW ? HIGH : LOW));
#elif DRIVE_MODE == DRIVE_SERVO_PWM
  CHECK(servo.pulse == SERVO_STOP_US);
#elif DRIVE_MODE == DRIVE_ANALOG_PWM
  CHECK(pwm[PWM_PIN] == 0); CHECK(pins[ENABLE_PIN] != ENABLE_ACTIVE_HIGH);
#elif DRIVE_MODE == DRIVE_STEP_DIR
  CHECK(frequencies[STEP_PIN] == 0); CHECK(pins[ENABLE_PIN] != ENABLE_ACTIVE_HIGH);
#elif DRIVE_MODE == DRIVE_28BYJ48
  for (int pin : BYJ48_PINS) CHECK(pins[pin] == LOW);
  CHECK(byj48CurrentSps == 0);
#endif
}

void protocolTests() {
  boot(); checkStoppedOutput(); advance(10000); checkStoppedOutput();
  send("  ping\r\n", "OK PING");
  send("speed 1\n", "OK SPEED"); CHECK(targetSpeed == 1);
  send("SPEED 100\n", "OK SPEED"); CHECK(targetSpeed == 100);
  for (const auto& bad : {"0", "101", "-1", "+1", "10abc", "1.5", "1 2", "9999999999"}) {
    send(std::string("SPEED ") + bad + "\n", "ERR SPEED"); CHECK(targetSpeed == 100);
  }
  send("SPEED\n", "ERR"); send("RUN extra\n", "ERR"); send("\n", "ERR");
  send("DIR R\n", "OK DIR"); CHECK(reverse);
  send("DIR F\n", "OK DIR"); CHECK(!reverse);
  send("ALARM\n", "OK ALARM"); CHECK(alarmOn);
  send("QUIET\n", "OK QUIET"); CHECK(!alarmOn);
  send("xxxxxxxxxxxxxxxxxRUN\n", "ERR"); checkStoppedOutput();
  send("RU\x01N\n", "ERR"); checkStoppedOutput();
  send("PING\n", "OK PING"); // recupera después de marco corrupto

#if DRIVE_MODE == DRIVE_28BYJ48 && !BYJ48_LED_SIMULATION && !BYJ48_HARDWARE_CONFIRMED
  unsigned long before = lastCommand;
  advance(100); send("RUN\n", "ERR HARDWARE UNCONFIRMED");
  CHECK(lastCommand == before); advance(5000); checkStoppedOutput();
#else
  // RUN completo es el único inicio; fragmentos no renuevan el plazo.
  Serial.inject("RU"); loop(); checkStoppedOutput();
  send("N\n", "OK RUN"); CHECK(running);
  advance(100); send("RUN\n", "OK RUN");
#if DRIVE_MODE == DRIVE_28BYJ48
  CHECK(byj48CurrentSps > 0); // RUN repetido no reinicia la rampa
#else
  CHECK(currentSpeed > 0);
#endif
  send("DIR R\n", "ERR DIR RUNNING"); CHECK(!reverse);
  // Cada rechazo, basura desbordada y línea vacía deja intacto el watchdog.
  const auto acceptedAt = lastCommand;
  for (int i = 0; i < 19; ++i) {
    advance(100);
    send("SPEED 10x\n", "ERR SPEED"); send("DIR R\n", "ERR DIR RUNNING");
    send("xxxxxxxxxxxxxxxxxPING\n", "ERR"); send("\n", "ERR");
    CHECK(lastCommand == acceptedAt); CHECK(running);
  }
  advance(100); checkStoppedOutput();
  send("PING\n", "OK PING"); advance(10); checkStoppedOutput();
  send("RUN\n", "OK RUN"); advance(1000, true); CHECK(running);
#if DRIVE_MODE == DRIVE_RELAY
  CHECK(pins[RELAY_PIN] == (RELAY_ACTIVE_LOW ? LOW : HIGH));
#elif DRIVE_MODE == DRIVE_SERVO_PWM
  CHECK(servo.pulse == SERVO_FWD_MAX_US);
#elif DRIVE_MODE == DRIVE_ANALOG_PWM
  CHECK(pwm[PWM_PIN] == 255); CHECK(pins[ENABLE_PIN] == ENABLE_ACTIVE_HIGH);
#elif DRIVE_MODE == DRIVE_STEP_DIR
  CHECK(frequencies[STEP_PIN] == STEP_MAX_HZ); CHECK(pins[ENABLE_PIN] == ENABLE_ACTIVE_HIGH);
#endif
  send("STOP\n", "OK STOP"); checkStoppedOutput(); advance(100); checkStoppedOutput();
  send("DIR R\n", "OK DIR"); CHECK(reverse);

  // Latido tardío no rescata la marcha que ya venció.
  send("RUN\n", "OK RUN"); clockUs += 2000000;
  send("PING\n", "OK PING"); checkStoppedOutput();
  // RX continuo sin LF no impide evaluar watchdog ni buzzer.
  send("RUN\n", "OK RUN");
  Serial.inject(std::string(10000, 'x')); clockUs += 2000000; loop();
  CHECK(Serial.available() > 0); checkStoppedOutput();

  // Rollover de millis (49.7 días) y recepción fragmentada.
  boot((static_cast<uint64_t>(UINT32_MAX) - 1000) * 1000);
  send("RUN\n", "OK RUN"); advance(1999); CHECK(running);
  Serial.inject("PI"); loop(); CHECK(running);
  advance(1); checkStoppedOutput();
#endif
}

#if DRIVE_MODE == DRIVE_28BYJ48 && (BYJ48_LED_SIMULATION || BYJ48_HARDWARE_CONFIRMED)
int phaseMask() { int mask = 0; for (int pin : BYJ48_PINS) mask = (mask << 1) | pins[pin]; return mask; }
void phaseTests() {
  boot(); send("SPEED 1\n", "OK SPEED"); send("RUN\n", "OK RUN");
  advance(250); CHECK(std::fabs(byj48CurrentSps - 40) < 0.01);
  send("STOP\n", "OK STOP");
  byj48PhaseValid = false; byj48Phase = 0;
  send("RUN\n", "OK RUN");
  // Controla solo reloj/tasa, usa updateByj48 real. Dos ciclos exactos.
  byj48CurrentSps = 40;
  const int expected[] = {8,12,4,6,2,3,1,9};
  for (int i = 0; i < 16; ++i) {
    clockUs += 24999; updateByj48();
    if (i == 0) CHECK(phaseMask() == 0);
    clockUs += 1; updateByj48(); CHECK(phaseMask() == expected[i % 8]);
    int before = phaseMask(); updateByj48(); CHECK(phaseMask() == before);
  }
  send("STOP\n", "OK STOP"); checkStoppedOutput();
  send("DIR R\n", "OK DIR"); send("RUN\n", "OK RUN"); byj48CurrentSps = 40;
  for (int i = 0; i < 8; ++i) {
    clockUs += 25000; updateByj48(); CHECK(phaseMask() == expected[(14 - i) % 8]);
  }
  // Pausa larga: una transición, sin ráfaga para recuperar pasos perdidos.
  clockUs += 500000; updateByj48(); int phase = byj48Phase;
  updateByj48(); CHECK(byj48Phase == phase);
  send("STOP\n", "OK STOP"); advance(200); CHECK(phaseMask() == 0);

  boot(); send("RUN\n", "OK RUN"); byj48CurrentSps = 400;
  clockUs += 2499; updateByj48(); CHECK(phaseMask() == 0);
  clockUs += 1; updateByj48(); CHECK(phaseMask() == 8); // máximo: 2.5 ms/fase
  clockUs += 2500; updateByj48(); CHECK(phaseMask() == 12);
  send("STOP\n", "OK STOP"); checkStoppedOutput();

  boot(); send("RUN\n", "OK RUN"); advance(2000, true);
  CHECK(std::fabs(byj48CurrentSps - 400) < 0.01);
  send("SPEED 1\n", "OK SPEED"); advance(500, true);
  CHECK(std::fabs(byj48CurrentSps - 300) < 0.01); // desacelera 200 SPS/s
  send("STOP\n", "OK STOP"); checkStoppedOutput(); // STOP no espera la rampa
  send("SPEED 1\n", "OK SPEED"); send("RUN\n", "OK RUN"); advance(500);
  CHECK(std::fabs(byj48CurrentSps - 40) < 0.01);
  send("SPEED 100\n", "OK SPEED"); advance(500);
  CHECK(std::fabs(byj48CurrentSps - 140) < 0.01);
  send("STOP\n", "OK STOP"); checkStoppedOutput();

  // Rollover micros (~71.6 min), sin salto de fase ni congelamiento.
  boot(static_cast<uint64_t>(UINT32_MAX) - 10000);
  send("RUN\n", "OK RUN"); byj48CurrentSps = 40;
  clockUs += 25000; updateByj48(); CHECK(phaseMask() == 8);
  clockUs += 25000; updateByj48(); CHECK(phaseMask() == 12);
}
#endif

int main() {
  protocolTests();
#if DRIVE_MODE == DRIVE_28BYJ48 && (BYJ48_LED_SIMULATION || BYJ48_HARDWARE_CONFIRMED)
  phaseTests();
#endif
  std::cout << "PASS mode=" << DRIVE_MODE << " LED=" << BYJ48_LED_SIMULATION
            << " confirmed=" << BYJ48_HARDWARE_CONFIRMED << "\n";
}
