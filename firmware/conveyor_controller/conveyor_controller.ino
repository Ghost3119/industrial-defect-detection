// Controlador de banda transportadora - Arduino / ESP32 (serial 115200).
//
// Sirve para casi cualquier motor: elige UNO en "TIPO DE MOTOR" (DRIVE_MODE).
//
//   DRIVE_RELAY       Relé/contactor (motor de CA/CC, banda con arranque simple).
//   DRIVE_SERVO_PWM   Servo de ROTACIÓN CONTINUA, ESC (brushless/cepillado) o
//                     servo-driver que se controla con pulso 1000-2000 us.
//   DRIVE_ANALOG_PWM  Driver con entrada PWM/analógica de velocidad (+ENABLE, +DIR):
//                     puentes H, servo-drivers con entrada 0-5 V (filtro RC), VFD.
//   DRIVE_STEP_DIR    Servo industrial o stepper con driver PUL/DIR/ENA.
//   DRIVE_28BYJ48     28BYJ-48 unipolar con ULN2003, cuatro señales de medio paso.
//
// NOTA: un servo hobby "de posición" (0-180°) no sirve para mover una banda; usa
// uno de rotación continua o un servo-driver con una de las opciones de arriba.
//
// Protocolo (una línea por comando, termina en \n; aceptados: "OK ...", rechazados: "ERR ..."):
//   RUN       -> arranca la banda (con rampa de aceleración)
//   STOP      -> detiene la banda de inmediato
//   PING      -> latido (heartbeat)
//   SPEED n   -> velocidad 1-100 % (28BYJ48: transición con rampa)
//   DIR F|R   -> sentido adelante / atrás (solo con la banda detenida)
//   ALARM     -> suena el buzzer (pieza mala; patrón intermitente)
//   QUIET     -> silencia el buzzer
//
// SEGURIDAD: si pasan WATCHDOG_MS sin recibir un comando VÁLIDO completo,
// la banda se detiene sola. Basura y comandos rechazados no renuevan el plazo. Al encender
// la banda SIEMPRE arranca detenida. Esto NO sustituye un paro de emergencia físico
// en el circuito de potencia del motor.
//
// Librerías: DRIVE_SERVO_PWM usa "Servo" (incluida en Arduino) o "ESP32Servo" (ESP32).
// DRIVE_STEP_DIR en ESP32 usa tone(): requiere el core arduino-esp32 3.x o superior.
// DRIVE_ANALOG_PWM usa analogWrite(): en ESP32 también requiere el core 3.x.

// ============================ 1. TIPO DE MOTOR ============================
#define DRIVE_RELAY       0
#define DRIVE_SERVO_PWM   1
#define DRIVE_ANALOG_PWM  2
#define DRIVE_STEP_DIR    3
#define DRIVE_28BYJ48      4

#ifndef DRIVE_MODE
#define DRIVE_MODE DRIVE_28BYJ48        // <-- cambia aquí (modos originales: 0-3)
#endif
#if DRIVE_MODE < DRIVE_RELAY || DRIVE_MODE > DRIVE_28BYJ48
#error "DRIVE_MODE no reconocido"
#endif

// Ambos en 0 por defecto: RUN queda bloqueado en el modo 28BYJ-48.
// LED_SIMULATION=1 SOLO con LED/simulador y sin motor conectado.
// HARDWARE_CONFIRMED=1 SOLO después de confirmar ULN2003, motor 5 V y fuente.
#ifndef BYJ48_LED_SIMULATION
#define BYJ48_LED_SIMULATION 0
#endif
#ifndef BYJ48_HARDWARE_CONFIRMED
#define BYJ48_HARDWARE_CONFIRMED 0
#endif

// ============================ 2. PINES ====================================
#if defined(ESP32)
  const int RELAY_PIN  = 26;   // DRIVE_RELAY
  const int SERVO_PIN  = 25;   // DRIVE_SERVO_PWM (señal)
  const int PWM_PIN    = 25;   // DRIVE_ANALOG_PWM (velocidad)
  const int STEP_PIN   = 25;   // DRIVE_STEP_DIR (PUL)
  const int DIR_PIN    = 27;   // DRIVE_ANALOG_PWM / DRIVE_STEP_DIR
  const int ENABLE_PIN = 14;   // DRIVE_ANALOG_PWM / DRIVE_STEP_DIR (-1 = sin pin)
  const int BUZZER_PIN = 33;   // buzzer (-1 = sin buzzer)
#else                          // Arduino Uno/Nano/Mega
  const int RELAY_PIN  = 7;
  const int SERVO_PIN  = 9;
  const int PWM_PIN    = 9;    // debe ser pin PWM
  const int STEP_PIN   = 9;
  const int DIR_PIN    = 8;
  const int ENABLE_PIN = 10;
  const int BUZZER_PIN = 6;
#endif

#if DRIVE_MODE == DRIVE_28BYJ48
  #if !defined(ESP32)
    #error "DRIVE_28BYJ48 requiere ESP32 y GPIO18/19/21/22"
  #endif
  const int BYJ48_PINS[4] = {18, 19, 21, 22}; // IN1, IN2, IN3, IN4 del ULN2003
#endif

// ============================ 3. AJUSTES POR TIPO ==========================
// ---- DRIVE_RELAY
const bool RELAY_ACTIVE_LOW = true;     // la mayoría de módulos de relé se activan con LOW
// (El relé no tiene velocidad: SPEED se ignora.)

// ---- DRIVE_SERVO_PWM   (microsegundos)
const int SERVO_STOP_US    = 1500;      // pulso de paro (calíbralo hasta que no gire)
const int SERVO_FWD_MAX_US = 2000;      // pulso a 100 % adelante
const int SERVO_REV_MAX_US = 1000;      // pulso a 100 % atrás (= STOP_US en ESC sin reversa)
const int SERVO_DEADBAND_US = 0;        // zona muerta: salta este margen al arrancar (servos: ~10-30)
// ESC sin reversa: STOP=1000, FWD_MAX=2000, REV_MAX=1000.

// ---- DRIVE_ANALOG_PWM / DRIVE_STEP_DIR
const bool ENABLE_ACTIVE_HIGH = true;   // nivel que HABILITA el driver
const bool DIR_FWD_LEVEL      = HIGH;   // nivel de DIR para "adelante"
const unsigned long STEP_MAX_HZ = 5000; // frecuencia de pulsos a 100 % (Uno: <= ~10000)
const unsigned long STEP_MIN_HZ = 40;   // tone() en AVR no baja de ~31 Hz

// ---- DRIVE_28BYJ48: medios pasos por segundo, NO pulsos STEP_DIR ni RPM.
constexpr float BYJ48_MIN_SPS = 40.0f;      // SPEED 1 (ajustar con carga real)
constexpr float BYJ48_MAX_SPS = 400.0f;     // SPEED 100; punto inicial conservador
constexpr float BYJ48_ACCEL_SPS2 = 200.0f;  // aceleración y desaceleración de SPEED
static_assert(BYJ48_MIN_SPS > 0 && BYJ48_MAX_SPS >= BYJ48_MIN_SPS,
              "Rango de medios pasos invalido");
static_assert(BYJ48_ACCEL_SPS2 > 0, "La rampa 28BYJ48 debe ser positiva");

// ---- General
const unsigned long WATCHDOG_MS = 2000; // sin comandos -> paro
const unsigned long ACCEL_MS    = 800;  // rampa 0 -> velocidad objetivo al arrancar (0 = sin rampa)
const bool BUZZER_ACTIVE        = true; // true: buzzer activo (con oscilador); false: pasivo
const unsigned long BEEP_ON_MS  = 300, BEEP_OFF_MS = 300;

// ============================ CÓDIGO ======================================
#if DRIVE_MODE == DRIVE_SERVO_PWM
  #if defined(ESP32)
    #include <ESP32Servo.h>
  #else
    #include <Servo.h>
  #endif
  Servo servo;
#endif

bool running = false;
bool reverse = false;
bool alarmOn = false;
int targetSpeed = 100;                  // 1-100 %
float currentSpeed = 0;                 // % realmente aplicado (con rampa)
float lastApplied = -1;                 // evita reconfigurar la salida (p. ej. tone()) sin cambios
uint32_t lastCommand = 0, lastRampMs = 0;
String line;
const unsigned int MAX_COMMAND_LENGTH = 16;
bool discardLine = false;              // descarta TODO el marco corrupto hasta LF

#if DRIVE_MODE == DRIVE_28BYJ48
// Orden de columnas: IN1 IN2 IN3 IN4. Una o dos bobinas, nunca las cuatro.
const uint8_t BYJ48_HALF_STEPS[8][4] = {
  {1,0,0,0}, {1,1,0,0}, {0,1,0,0}, {0,1,1,0},
  {0,0,1,0}, {0,0,1,1}, {0,0,0,1}, {1,0,0,1}
};
float byj48CurrentSps = 0;
uint32_t byj48LastStepUs = 0;
uint8_t byj48Phase = 0;
bool byj48PhaseValid = false;

bool byj48OutputsAllowed() {
  return BYJ48_LED_SIMULATION || BYJ48_HARDWARE_CONFIRMED;
}

void releaseByj48() {
  for (int i = 0; i < 4; ++i) digitalWrite(BYJ48_PINS[i], LOW);
  byj48CurrentSps = 0;
  // Conserva el índice al reanudar; no implica posición mecánica conocida.
}

// A lo sumo UNA transición por loop; si se retrasa, no recupera pasos en ráfaga.
void updateByj48() {
  if (!running || !byj48OutputsAllowed() || byj48CurrentSps <= 0) return;
  uint32_t now = micros();
  uint32_t interval = (uint32_t)(1000000.0f / byj48CurrentSps);
  if ((uint32_t)(now - byj48LastStepUs) < interval) return;
  byj48LastStepUs = now;
  if (byj48PhaseValid) byj48Phase = (byj48Phase + (reverse ? 7 : 1)) % 8;
  byj48PhaseValid = true;
  for (int i = 0; i < 4; ++i)
    digitalWrite(BYJ48_PINS[i], BYJ48_HALF_STEPS[byj48Phase][i] ? HIGH : LOW);
}
#endif

// Aplica una velocidad (0-100 %) a la salida del tipo de motor elegido.
void applyOutput(float pct) {
  lastApplied = pct;
#if DRIVE_MODE == DRIVE_RELAY
  bool on = pct > 0;
  digitalWrite(RELAY_PIN, (on ^ RELAY_ACTIVE_LOW) ? HIGH : LOW);

#elif DRIVE_MODE == DRIVE_SERVO_PWM
  int us = SERVO_STOP_US;
  if (pct > 0) {
    int maxUs = reverse ? SERVO_REV_MAX_US : SERVO_FWD_MAX_US;
    int span = maxUs - SERVO_STOP_US;                       // negativo si es reversa
    int dead = (span >= 0) ? SERVO_DEADBAND_US : -SERVO_DEADBAND_US;
    us = SERVO_STOP_US + dead + (int)((span - dead) * pct / 100.0f);
  }
  servo.writeMicroseconds(us);

#elif DRIVE_MODE == DRIVE_ANALOG_PWM
  digitalWrite(DIR_PIN, (reverse ? !DIR_FWD_LEVEL : DIR_FWD_LEVEL) ? HIGH : LOW);
  if (ENABLE_PIN >= 0) digitalWrite(ENABLE_PIN, (pct > 0) == ENABLE_ACTIVE_HIGH ? HIGH : LOW);
  analogWrite(PWM_PIN, (int)(pct * 255.0f / 100.0f));

#elif DRIVE_MODE == DRIVE_STEP_DIR
  digitalWrite(DIR_PIN, (reverse ? !DIR_FWD_LEVEL : DIR_FWD_LEVEL) ? HIGH : LOW);
  if (pct > 0) {
    unsigned long hz = STEP_MIN_HZ + (unsigned long)((STEP_MAX_HZ - STEP_MIN_HZ) * pct / 100.0f);
    if (ENABLE_PIN >= 0) digitalWrite(ENABLE_PIN, ENABLE_ACTIVE_HIGH ? HIGH : LOW);
    tone(STEP_PIN, hz);
  } else {
    noTone(STEP_PIN);
    if (ENABLE_PIN >= 0) digitalWrite(ENABLE_PIN, ENABLE_ACTIVE_HIGH ? LOW : HIGH);
  }
#elif DRIVE_MODE == DRIVE_28BYJ48
  // Los tiempos y fases se atienden en updateByj48(), nunca con tone()/delay().
  if (pct <= 0 || !byj48OutputsAllowed()) releaseByj48();
#endif
}

void setBelt(bool on) {
  running = on;
  if (on) {
#if DRIVE_MODE == DRIVE_28BYJ48
    byj48CurrentSps = 0;
    byj48LastStepUs = micros();
    currentSpeed = 0;
    lastRampMs = millis();
#else
    currentSpeed = (ACCEL_MS == 0) ? targetSpeed : 0.0f;    // con rampa: arranca en 0 y sube
    lastRampMs = millis();
    if (ACCEL_MS == 0) applyOutput(currentSpeed);
    else applyOutput(1);                                     // primer empuje mínimo
#endif
  } else {
    currentSpeed = 0;                                        // el paro NUNCA usa rampa
    applyOutput(0);
  }
}

// Rampa hacia targetSpeed (28BYJ48 también desacelera los cambios de SPEED).
void updateRamp() {
  if (!running) return;
  uint32_t now = millis();
  float dt = (float)(uint32_t)(now - lastRampMs);
  lastRampMs = now;
#if DRIVE_MODE == DRIVE_28BYJ48
  float targetSps = BYJ48_MIN_SPS + (BYJ48_MAX_SPS - BYJ48_MIN_SPS)
                    * (targetSpeed - 1) / 99.0f;
  float delta = dt * BYJ48_ACCEL_SPS2 / 1000.0f;
  if (byj48CurrentSps < targetSps)
    byj48CurrentSps = min(byj48CurrentSps + delta, targetSps);
  else if (byj48CurrentSps > targetSps)
    byj48CurrentSps = max(byj48CurrentSps - delta, targetSps);
#else
  if (currentSpeed > targetSpeed) currentSpeed = targetSpeed;           // bajar: inmediato
  else if (currentSpeed < targetSpeed) {
    currentSpeed += (ACCEL_MS == 0) ? 100.0f : dt * 100.0f / ACCEL_MS;
    if (currentSpeed > targetSpeed) currentSpeed = targetSpeed;
  }
  if (currentSpeed != lastApplied) applyOutput(currentSpeed);
#endif
}

// Buzzer sin bloquear el loop (y sin tone(), que en AVR solo admite un pin a la vez).
void updateBuzzer() {
  if (BUZZER_PIN < 0) return;
  bool sounding = alarmOn && ((millis() % (BEEP_ON_MS + BEEP_OFF_MS)) < BEEP_ON_MS);
  if (BUZZER_ACTIVE) {
    digitalWrite(BUZZER_PIN, sounding ? HIGH : LOW);
  } else if (sounding) {
    digitalWrite(BUZZER_PIN, (micros() / 250) % 2 ? HIGH : LOW);       // ~2 kHz
  } else {
    digitalWrite(BUZZER_PIN, LOW);
  }
}

bool handleCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();
  if (cmd == "RUN") {
#if DRIVE_MODE == DRIVE_28BYJ48
    if (!byj48OutputsAllowed()) {
      Serial.println("ERR HARDWARE UNCONFIRMED");
      return false;
    }
#endif
    if (!running) setBelt(true); // RUN repetido funciona como latido sin reiniciar la rampa
    Serial.println("OK RUN");
  }
  else if (cmd == "STOP")  { setBelt(false); Serial.println("OK STOP"); }
  else if (cmd == "PING")  { Serial.println("OK PING"); }
  else if (cmd == "ALARM") { alarmOn = true;  Serial.println("OK ALARM"); }
  else if (cmd == "QUIET") { alarmOn = false; Serial.println("OK QUIET"); }
  else if (cmd.startsWith("SPEED ")) {
    String value = cmd.substring(6);
    int v = 0;
    bool valid = value.length() > 0 && value.length() <= 3;
    for (unsigned int i = 0; valid && i < value.length(); ++i) {
      if (value[i] < '0' || value[i] > '9') { valid = false; break; }
      v = v * 10 + (value[i] - '0');
    }
    if (valid && v >= 1 && v <= 100) { targetSpeed = v; Serial.println("OK SPEED"); }
    else { Serial.println("ERR SPEED"); return false; }
  }
  else if (cmd == "DIR F" || cmd == "DIR R") {
    if (!running) { reverse = (cmd == "DIR R"); Serial.println("OK DIR"); }
    else { Serial.println("ERR DIR RUNNING"); return false; }
  }
  else { Serial.println("ERR"); return false; }
  return true;
}

void setup() {
#if DRIVE_MODE == DRIVE_RELAY
  digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? HIGH : LOW);
  pinMode(RELAY_PIN, OUTPUT);
#elif DRIVE_MODE == DRIVE_SERVO_PWM
  servo.attach(SERVO_PIN, min(SERVO_REV_MAX_US, SERVO_STOP_US) - 100, max(SERVO_FWD_MAX_US, SERVO_STOP_US) + 100);
#elif DRIVE_MODE == DRIVE_ANALOG_PWM || DRIVE_MODE == DRIVE_STEP_DIR
  pinMode(DIR_PIN, OUTPUT);
  if (ENABLE_PIN >= 0) pinMode(ENABLE_PIN, OUTPUT);
  pinMode(DRIVE_MODE == DRIVE_ANALOG_PWM ? PWM_PIN : STEP_PIN, OUTPUT);
#elif DRIVE_MODE == DRIVE_28BYJ48
  for (int i = 0; i < 4; ++i) {
    digitalWrite(BYJ48_PINS[i], LOW);
    pinMode(BYJ48_PINS[i], OUTPUT);
  }
#endif
  if (BUZZER_PIN >= 0) { pinMode(BUZZER_PIN, OUTPUT); digitalWrite(BUZZER_PIN, LOW); }
  setBelt(false);
  Serial.begin(115200);
}

void loop() {
  // Parar antes de aceptar un latido tardío; aritmética sin signo tolera rollover.
  if (running && (uint32_t)(millis() - lastCommand) >= WATCHDOG_MS)
    setBelt(false);
  // Presupuesto acotado: basura continua no puede monopolizar el loop.
  unsigned int serialBudget = 32;
  while (Serial.available() && serialBudget-- > 0) {
    char c = Serial.read();
    if (c == '\n') {
      if (discardLine) Serial.println("ERR");
      else if (handleCommand(line)) lastCommand = millis();
      line = "";
      discardLine = false;
    } else if (c != '\r' && !discardLine) {
      if (c < 32 || c > 126 || line.length() >= MAX_COMMAND_LENGTH) {
        discardLine = true;
        line = "";
      } else line += c;
    }
  }
  if (running && (uint32_t)(millis() - lastCommand) >= WATCHDOG_MS) {
    setBelt(false);                                 // sin latido: paro por seguridad
  }
  updateRamp();
#if DRIVE_MODE == DRIVE_28BYJ48
  updateByj48();
#endif
  updateBuzzer();
}
