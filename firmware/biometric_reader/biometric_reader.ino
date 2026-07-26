/*
 * SmartAttend Biometric Reader — Arduino Firmware
 *
 * Hardware: AS608 fingerprint sensor + Arduino (Uno/Mega/Nano)
 * Library:  Adafruit Fingerprint Sensor Library
 *
 * Serial protocol (9600 baud, newline-delimited):
 *
 *   Python → Arduino:
 *     ENROLL:<id>              Start enrollment with given fingerprint ID
 *     DELETE:<id>               Delete fingerprint template
 *     VERIFY:<id>               Verify a finger against a specific ID
 *     ATTENDANCE                Switch to attendance (verify) mode
 *     DEVICE_STATUS             Report mode, template count, firmware
 *     RESTART                   Software restart
 *     DELETE_ALL                Delete all stored templates
 *     GET_COUNT                 Report stored template count
 *
 *   Arduino → Python:
 *     ENROLL_PROGRESS:<step>:<message>  Enrollment step update
 *     ENROLL_SUCCESS:<id>               Enrollment completed
 *     ENROLL_FAIL:<message>             Enrollment failed
 *     DELETED:<id>                      Template deleted
 *     DELETE_FAIL:<message>             Deletion failed
 *     MATCH:<id>:<score>                Fingerprint matched
 *     NO_MATCH                          No match found
 *     STATUS:<mode>:<template_count>:<firmware>
 *     ACK:<command>                     Command acknowledged
 *     ERROR:<message>                   Error
 *     INFO:<message>                    Informational
 */

#include <Adafruit_Fingerprint.h>
#include <SoftwareSerial.h>

// ─── Pin Configuration ───────────────────────────────────────────────────────
// AS608 sensor connected to hardware Serial1 on boards that have it (Mega, Due, etc.)
// On Uno/Nano, use SoftwareSerial:
//   TX ( Arduino pin 2 ) → RX ( AS608 white wire )
//   RX ( Arduino pin 3 ) → TX ( AS608 green wire )
//
// Set USE_SOFTWARE_SERIAL to 1 for Uno/Nano, 0 for Mega/Due/boards with Serial1.

#define USE_SOFTWARE_SERIAL 1

#if USE_SOFTWARE_SERIAL
  SoftwareSerial mySerial(2, 3);  // RX, TX
  Adafruit_Fingerprint finger(&mySerial);
#else
  // Mega/Due — AS608 on Serial1 (pins 18/19)
  Adafruit_Fingerprint finger(&Serial1);
#endif

// ─── Constants ───────────────────────────────────────────────────────────────

#define FIRMWARE_VERSION   "1.0.0"
#define BAUD_RATE          9600
#define CMD_BUFFER_SIZE    64

// Custom return code for enrollment timeout (not in Adafruit library)
#define RESULT_TIMEOUT     100

// ─── State ───────────────────────────────────────────────────────────────────

enum Mode {
  MODE_ATTENDANCE,
  MODE_ENROLLMENT,
  MODE_DELETION,
  MODE_MAINTENANCE
};

volatile Mode currentMode = MODE_ATTENDANCE;
char cmdBuffer[CMD_BUFFER_SIZE];
uint8_t cmdIndex = 0;

// ─── Forward Declarations ────────────────────────────────────────────────────

void handleCommand(const String &cmd);
void cmdEnroll(int id);
void cmdDelete(int id);
void cmdVerify(int id);
void cmdDeviceStatus();
void cmdDeleteAll();
void cmdGetCount();
void sendLine(const String &msg);
uint8_t getFingerprintEnroll(int id);

// ═══════════════════════════════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════════════════════════════

void setup() {
  Serial.begin(BAUD_RATE);
  finger.begin(57600);

  if (finger.verifyPassword()) {
    sendLine("INFO:Sensor connected OK");
  } else {
    sendLine("ERROR:Sensor not found - check wiring");
    // Halt — nothing works without the sensor
    while (1) { delay(1000); }
  }

  finger.getTemplateCount();
  sendLine("STATUS:ATTENDANCE:" + String(finger.templateCount) + ":" + FIRMWARE_VERSION);
  sendLine("INFO:System ready");
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN LOOP — reads serial commands, dispatches to current mode
// ═══════════════════════════════════════════════════════════════════════════════

void loop() {
  // ── 1. Read incoming serial commands ──
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdIndex > 0) {
        cmdBuffer[cmdIndex] = '\0';
        handleCommand(String(cmdBuffer));
        cmdIndex = 0;
      }
    } else if (cmdIndex < CMD_BUFFER_SIZE - 1) {
      cmdBuffer[cmdIndex++] = c;
    }
  }

  // ── 2. Mode-specific behavior ──
  if (currentMode == MODE_ATTENDANCE) {
    // Quick attendance scan
    int8_t result = finger.getImage();
    if (result == FINGERPRINT_OK) {
      result = finger.image2Tz();
      if (result == FINGERPRINT_OK) {
        result = finger.fingerFastSearch();
        if (result == FINGERPRINT_OK) {
          // Match found
          sendLine("MATCH:" + String(finger.fingerID) + ":" + String(finger.confidence));
          delay(1000);  // debounce — wait for finger to lift
        } else {
          sendLine("NO_MATCH");
        }
      }
    }
    // No finger detected — just loop
  }

  // In ENROLLMENT/DELETION mode, commands drive everything.
  // The loop just polls for serial input.

  delay(50);
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMMAND PARSER
// ═══════════════════════════════════════════════════════════════════════════════

void handleCommand(const String &cmd) {
  // ── ENROLL:<id> ──
  if (cmd.startsWith("ENROLL:")) {
    int id = cmd.substring(7).toInt();
    if (id < 1 || id > 127) {
      sendLine("ENROLL_FAIL:Invalid ID " + String(id) + " (must be 1-127)");
      return;
    }
    sendLine("ACK:ENROLL");
    currentMode = MODE_ENROLLMENT;
    cmdEnroll(id);
    // cmdEnroll is blocking — when it returns we go back to attendance
    return;
  }

  // ── DELETE:<id> ──
  if (cmd.startsWith("DELETE:")) {
    int id = cmd.substring(7).toInt();
    if (id < 1 || id > 127) {
      sendLine("DELETE_FAIL:Invalid ID");
      return;
    }
    sendLine("ACK:DELETE");
    cmdDelete(id);
    return;
  }

  // ── VERIFY:<id> ──
  if (cmd.startsWith("VERIFY:")) {
    int id = cmd.substring(7).toInt();
    sendLine("ACK:VERIFY");
    cmdVerify(id);
    return;
  }

  // ── ATTENDANCE ──
  if (cmd == "ATTENDANCE") {
    sendLine("ACK:ATTENDANCE");
    currentMode = MODE_ATTENDANCE;
    finger.getTemplateCount();
    sendLine("STATUS:ATTENDANCE:" + String(finger.templateCount) + ":" + FIRMWARE_VERSION);
    return;
  }

  // ── DEVICE_STATUS ──
  if (cmd == "DEVICE_STATUS") {
    sendLine("ACK:DEVICE_STATUS");
    cmdDeviceStatus();
    return;
  }

  // ── RESTART ──
  if (cmd == "RESTART") {
    sendLine("ACK:RESTART");
    delay(200);
    asm volatile("jmp 0x0000");  // software reset on AVR
    return;
  }

  // ── DELETE_ALL ──
  if (cmd == "DELETE_ALL") {
    sendLine("ACK:DELETE_ALL");
    cmdDeleteAll();
    return;
  }

  // ── GET_COUNT ──
  if (cmd == "GET_COUNT") {
    sendLine("ACK:GET_COUNT");
    cmdGetCount();
    return;
  }

  // Unknown command
  sendLine("ERROR:Unknown command: " + cmd);
}

// ═══════════════════════════════════════════════════════════════════════════════
// ENROLLMENT
// ═══════════════════════════════════════════════════════════════════════════════

void cmdEnroll(int id) {
  sendLine("ENROLL_PROGRESS:1:Place your finger on the sensor");

  uint8_t result = getFingerprintEnroll(id);

  if (result == FINGERPRINT_OK) {
    finger.getTemplateCount();
    sendLine("ENROLL_SUCCESS:" + String(id));
    sendLine("STATUS:ATTENDANCE:" + String(finger.templateCount) + ":" + FIRMWARE_VERSION);
  } else if (result == RESULT_TIMEOUT) {
    sendLine("ENROLL_FAIL:Enrollment timed out");
  } else {
    sendLine("ENROLL_FAIL:Enrollment failed (error " + String(result) + ")");
  }

  currentMode = MODE_ATTENDANCE;
}

/*
 * Full enrollment sequence matching the Adafruit library workflow.
 * Returns FINGERPRINT_OK on success, RESULT_TIMEOUT on timeout.
 *
 * Steps (reported back to Python):
 *   1 — Place finger (first scan)
 *   2 — Remove finger
 *   3 — Place same finger again (second scan)
 *   4 — Processing / storing
 */
uint8_t getFingerprintEnroll(int id) {
  int p = -1;

  // ── Step 1: First image ──
  sendLine("ENROLL_PROGRESS:1:Place your finger on the sensor");

  unsigned long start = millis();
  while (p != FINGERPRINT_OK) {
    p = finger.getImage();
    if (millis() - start > 15000) {
      return RESULT_TIMEOUT;  // 15-second timeout
    }
    delay(100);
  }

  p = finger.image2Tz(1);
  if (p != FINGERPRINT_OK) {
    sendLine("ENROLL_FAIL:Failed to process first image");
    return p;
  }

  sendLine("ENROLL_PROGRESS:2:Remove your finger from the sensor");
  delay(2000);

  // ── Step 2: Wait for finger removal ──
  p = 0;
  start = millis();
  while (p != FINGERPRINT_NOFINGER) {
    p = finger.getImage();
    if (millis() - start > 10000) {
      return RESULT_TIMEOUT;
    }
    delay(100);
  }

  // ── Step 3: Second image ──
  sendLine("ENROLL_PROGRESS:3:Place the same finger again");

  p = -1;
  start = millis();
  while (p != FINGERPRINT_OK) {
    p = finger.getImage();
    if (millis() - start > 15000) {
      return RESULT_TIMEOUT;
    }
    delay(100);
  }

  p = finger.image2Tz(2);
  if (p != FINGERPRINT_OK) {
    sendLine("ENROLL_FAIL:Failed to process second image");
    return p;
  }

  // ── Step 4: Create model and store ──
  sendLine("ENROLL_PROGRESS:4:Processing fingerprint...");

  p = finger.createModel();
  if (p == FINGERPRINT_OK) {
    // Fingerprints match
  } else if (p == FINGERPRINT_ENROLLMISMATCH) {
    sendLine("ENROLL_FAIL:Fingerprints did not match - try again");
    return p;
  } else {
    sendLine("ENROLL_FAIL:Failed to create model");
    return p;
  }

  p = finger.storeModel(id);
  if (p == FINGERPRINT_OK) {
    sendLine("ENROLL_PROGRESS:4:Template stored successfully");
    return FINGERPRINT_OK;
  } else {
    sendLine("ENROLL_FAIL:Failed to store template");
    return p;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// DELETE
// ═══════════════════════════════════════════════════════════════════════════════

void cmdDelete(int id) {
  uint8_t p = finger.deleteModel(id);
  if (p == FINGERPRINT_OK) {
    sendLine("DELETED:" + String(id));
  } else {
    sendLine("DELETE_FAIL:Failed to delete template " + String(id));
  }
  currentMode = MODE_ATTENDANCE;
}

void cmdDeleteAll() {
  uint8_t p = finger.emptyDatabase();
  if (p == FINGERPRINT_OK) {
    sendLine("INFO:All templates deleted");
  } else {
    sendLine("ERROR:Failed to clear database");
  }
  currentMode = MODE_ATTENDANCE;
}

// ═══════════════════════════════════════════════════════════════════════════════
// VERIFY
// ═══════════════════════════════════════════════════════════════════════════════

void cmdVerify(int id) {
  sendLine("INFO:Place finger to verify against ID " + String(id));

  int p = -1;
  unsigned long start = millis();
  while (p != FINGERPRINT_OK) {
    p = finger.getImage();
    if (millis() - start > 10000) {
      sendLine("ERROR:Verify timed out");
      currentMode = MODE_ATTENDANCE;
      return;
    }
    delay(100);
  }

  p = finger.image2Tz();
  if (p != FINGERPRINT_OK) {
    sendLine("ERROR:Failed to process image");
    currentMode = MODE_ATTENDANCE;
    return;
  }

  p = finger.fingerFastSearch();
  if (p == FINGERPRINT_OK) {
    if (finger.fingerID == id) {
      sendLine("MATCH:" + String(finger.fingerID) + ":" + String(finger.confidence));
    } else {
      sendLine("NO_MATCH");
    }
  } else {
    sendLine("NO_MATCH");
  }

  currentMode = MODE_ATTENDANCE;
}

// ═══════════════════════════════════════════════════════════════════════════════
// DEVICE STATUS
// ═══════════════════════════════════════════════════════════════════════════════

void cmdDeviceStatus() {
  finger.getTemplateCount();

  const char *modeStr;
  switch (currentMode) {
    case MODE_ATTENDANCE:  modeStr = "ATTENDANCE";  break;
    case MODE_ENROLLMENT:  modeStr = "ENROLLMENT";  break;
    case MODE_DELETION:    modeStr = "DELETION";    break;
    case MODE_MAINTENANCE: modeStr = "MAINTENANCE"; break;
    default:               modeStr = "ATTENDANCE";  break;
  }

  sendLine("STATUS:" + String(modeStr) + ":" + String(finger.templateCount) + ":" + FIRMWARE_VERSION);
}

// ═══════════════════════════════════════════════════════════════════════════════
// GET COUNT
// ═══════════════════════════════════════════════════════════════════════════════

void cmdGetCount() {
  finger.getTemplateCount();
  sendLine("INFO:Template count " + String(finger.templateCount));
}

// ═══════════════════════════════════════════════════════════════════════════════
// UTILITY
// ═══════════════════════════════════════════════════════════════════════════════

void sendLine(const String &msg) {
  Serial.println(msg);
}
