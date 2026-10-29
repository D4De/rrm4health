/*
  ESP32-C3 Super Mini + HW-123 / MPU6050
  WiFi RAW / FEATURES firmware

  This firmware is designed to be protocol-compatible with the current
  Connect_WIFI.py manager used by the project.

  Hardware
  --------
  ESP32-C3 Super Mini      HW-123 / MPU6050
  3V3                  -> VCC
  GND                  -> GND
  GPIO3                -> SDA
  GPIO4                -> SCL

  Arduino IDE
  -----------
  Board: ESP32C3 Dev Module
  USB CDC On Boot: Enabled

  WiFi protocol
  -------------
  TCP port: 8023

  Commands accepted from Connect_WIFI.py:
      PING
      HELLO
      BYE
      BOOT_ID
      BATTERY
      TIMESTAMP:<unix_timestamp>
      CONFIG:sampling_frequency=...,raw=true/false,window_size=...,step_size=...
      ACTIVITY:START
      ACTIVITY:STOP

  Acquisition modes
  -----------------
      raw=true
          RAW packet:
              9 x uint16  (Ax Ay Az Gx Gy Gz Mx My Mz)
              uint16      counter
              uint32      timestamp

          MPU6050 has no magnetometer, therefore:
              Mx = My = Mz = 0

      raw=false
          FEATURES packet:
              FEATURE_COUNT x float32
              uint16 counter
              uint32 timestamp

  Sensor configuration
  --------------------
      Accelerometer range: +/-4 g
      Gyroscope range:     +/-2000 deg/s
      DLPF_CFG:            3
      I2C clock:           400 kHz

  With DLPF_CFG=3, the MPU6050 internal sample-rate base is 1000 Hz:
      Fs = 1000 / (1 + SMPLRT_DIV)

  Example:
      Fs = 200 Hz -> SMPLRT_DIV = 4
*/

#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <math.h>

// =============================================================================
// USER / HARDWARE CONFIGURATION
// =============================================================================

#define SDA_PIN                         3
#define SCL_PIN                         4

#define MPU6050_ADDR                    0x68

#define WIFI_SSID                       "XXXXX"
#define WIFI_PASSWORD                   "XXXXX"

#define TCP_PORT                        8023

#define RECONNECT_TIMEOUT_MS            30000UL

#define DEFAULT_SAMPLING_FREQUENCY      200
#define MAX_IMU_SAMPLING_FREQUENCY      1000

#define DEFAULT_WINDOW_SIZE             300
#define DEFAULT_STEP_SIZE               100

#define CAMPAIGN_RAW                    0x00
#define CAMPAIGN_FEATURES               0x01

#define FEATURE_COUNT                   28

// Keep these ranges aligned with the LSM6DS3 gait-analysis configuration.
#define ACCEL_FS_SEL                    1       // +/-4 g
#define GYRO_FS_SEL                     3       // +/-2000 deg/s
#define DLPF_CFG                        3       // 1 kHz base rate

#define FEATURE_FILTER_ENABLED          1

// Existing feature filter coefficients used by the other IMU firmware.
const float FEATURE_B0 = 0.04613188f;
const float FEATURE_B1 = 0.09226376f;
const float FEATURE_B2 = 0.04613188f;
const float FEATURE_A1 = -1.30728503f;
const float FEATURE_A2 = 0.49181255f;

// =============================================================================
// MPU6050 REGISTERS
// =============================================================================

#define REG_SMPLRT_DIV                  0x19
#define REG_CONFIG                      0x1A
#define REG_GYRO_CONFIG                 0x1B
#define REG_ACCEL_CONFIG                0x1C
#define REG_INT_ENABLE                  0x38
#define REG_INT_STATUS                  0x3A
#define REG_ACCEL_XOUT_H                0x3B
#define REG_PWR_MGMT_1                  0x6B
#define REG_WHO_AM_I                    0x75

// =============================================================================
// PACKETS
// =============================================================================

typedef struct __attribute__((packed)) {
  uint16_t ax;
  uint16_t ay;
  uint16_t az;

  uint16_t gx;
  uint16_t gy;
  uint16_t gz;

  uint16_t mx;
  uint16_t my;
  uint16_t mz;

  uint16_t counter;
  uint32_t timestamp;
} datapacket_t;

static_assert(
  sizeof(datapacket_t) == 24,
  "Unexpected RAW packet size"
);

typedef struct __attribute__((packed)) {
  float features[FEATURE_COUNT];
  uint16_t counter;
  uint32_t timestamp;
} featurepacket_t;

static_assert(
  sizeof(featurepacket_t) == 118,
  "Unexpected FEATURES packet size"
);

// =============================================================================
// CAMPAIGN
// =============================================================================

typedef struct {
  uint16_t sampling_frequency;
  uint8_t mode;
  uint16_t window_size;
  uint16_t step_size;
} campaign_parameters_t;

campaign_parameters_t campaign_settings = {
  DEFAULT_SAMPLING_FREQUENCY,
  CAMPAIGN_RAW,
  DEFAULT_WINDOW_SIZE,
  DEFAULT_STEP_SIZE
};

uint16_t counter = 0;

bool timestampReceived = false;
bool configurationReceived = false;
bool campaignOngoing = false;

// Timestamp received from the Python manager.
uint32_t initTimestamp = 0;
uint32_t baseMillis = 0;

// =============================================================================
// WIFI
// =============================================================================

WiFiServer server(TCP_PORT);
WiFiClient client;

// Stable human-readable IMU identifier generated from the last 4 hex
// digits of the ESP32-C3 WiFi MAC address.
// Example: MAC AA:BB:CC:DD:78:11 -> IMU7811
String imu_id = "";

uint32_t boot_id = 0;
uint32_t disconnectStartMs = 0;
bool reconnectTimerActive = false;

// =============================================================================
// FEATURE BUFFERS
// =============================================================================

class FeatureBiquadFilter {
 private:
  float x1 = 0.0f;
  float x2 = 0.0f;
  float y1 = 0.0f;
  float y2 = 0.0f;

 public:
  void reset() {
    x1 = x2 = y1 = y2 = 0.0f;
  }

  float process(float x) {
    float y =
      FEATURE_B0 * x +
      FEATURE_B1 * x1 +
      FEATURE_B2 * x2 -
      FEATURE_A1 * y1 -
      FEATURE_A2 * y2;

    x2 = x1;
    x1 = x;
    y2 = y1;
    y1 = y;

    return y;
  }
};

FeatureBiquadFilter featureFilterAx;
FeatureBiquadFilter featureFilterAy;
FeatureBiquadFilter featureFilterAz;

FeatureBiquadFilter featureFilterGx;
FeatureBiquadFilter featureFilterGy;
FeatureBiquadFilter featureFilterGz;

float *featureAxBuffer = nullptr;
float *featureAyBuffer = nullptr;
float *featureAzBuffer = nullptr;

float *featureGxBuffer = nullptr;
float *featureGyBuffer = nullptr;
float *featureGzBuffer = nullptr;

uint16_t featureSampleCount = 0;
bool featureBuffersReady = false;

// =============================================================================
// MPU6050 LOW LEVEL
// =============================================================================

bool mpuWriteRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(reg);
  Wire.write(value);

  return Wire.endTransmission() == 0;
}

bool mpuReadRegister(uint8_t reg, uint8_t &value) {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(reg);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(MPU6050_ADDR, (uint8_t)1) != 1) {
    return false;
  }

  value = Wire.read();

  return true;
}

bool mpuReadBurst(
  uint8_t startRegister,
  uint8_t *buffer,
  size_t length
) {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(startRegister);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  size_t received = Wire.requestFrom(
    MPU6050_ADDR,
    (uint8_t)length
  );

  if (received != length) {
    return false;
  }

  for (size_t i = 0; i < length; i++) {
    buffer[i] = Wire.read();
  }

  return true;
}

bool mpuDevicePresent() {
  Wire.beginTransmission(MPU6050_ADDR);

  return Wire.endTransmission() == 0;
}

float getMPUBaseSampleRateHz() {
  if (DLPF_CFG == 0 || DLPF_CFG == 7) {
    return 8000.0f;
  }

  return 1000.0f;
}

uint8_t calculateSampleRateDivider(uint16_t requestedHz) {
  float baseRate = getMPUBaseSampleRateHz();

  float divider =
    (baseRate / (float)requestedHz) - 1.0f;

  if (divider < 0.0f) {
    divider = 0.0f;
  }

  if (divider > 255.0f) {
    divider = 255.0f;
  }

  return (uint8_t)(divider + 0.5f);
}

float calculateConfiguredSampleRate(
  uint8_t divider
) {
  return getMPUBaseSampleRateHz() /
         (1.0f + divider);
}

float accelSensitivityLSBPerG() {
  switch (ACCEL_FS_SEL) {
    case 0:
      return 16384.0f;

    case 1:
      return 8192.0f;

    case 2:
      return 4096.0f;

    case 3:
      return 2048.0f;
  }

  return 8192.0f;
}

float gyroSensitivityLSBPerDps() {
  switch (GYRO_FS_SEL) {
    case 0:
      return 131.0f;

    case 1:
      return 65.5f;

    case 2:
      return 32.8f;

    case 3:
      return 16.4f;
  }

  return 16.4f;
}

bool configureMPU6050(uint16_t requestedFrequency) {
  if (
    requestedFrequency == 0 ||
    requestedFrequency > MAX_IMU_SAMPLING_FREQUENCY
  ) {
    return false;
  }

  // Wake up and use gyro X PLL clock.
  if (!mpuWriteRegister(REG_PWR_MGMT_1, 0x01)) {
    return false;
  }

  delay(50);

  if (
    !mpuWriteRegister(
      REG_CONFIG,
      DLPF_CFG & 0x07
    )
  ) {
    return false;
  }

  uint8_t divider =
    calculateSampleRateDivider(
      requestedFrequency
    );

  if (
    !mpuWriteRegister(
      REG_SMPLRT_DIV,
      divider
    )
  ) {
    return false;
  }

  if (
    !mpuWriteRegister(
      REG_ACCEL_CONFIG,
      (ACCEL_FS_SEL & 0x03) << 3
    )
  ) {
    return false;
  }

  if (
    !mpuWriteRegister(
      REG_GYRO_CONFIG,
      (GYRO_FS_SEL & 0x03) << 3
    )
  ) {
    return false;
  }

  // DATA_RDY status / interrupt enable.
  if (
    !mpuWriteRegister(
      REG_INT_ENABLE,
      0x01
    )
  ) {
    return false;
  }

  Serial.print(
    "[IMU] Requested sampling frequency: "
  );
  Serial.print(requestedFrequency);
  Serial.println(" Hz");

  Serial.print(
    "[IMU] SMPLRT_DIV: "
  );
  Serial.println(divider);

  Serial.print(
    "[IMU] Configured sampling frequency: "
  );
  Serial.print(
    calculateConfiguredSampleRate(divider),
    2
  );
  Serial.println(" Hz");

  Serial.println(
    "[IMU] Accelerometer range: +/-4 g"
  );

  Serial.println(
    "[IMU] Gyroscope range: +/-2000 deg/s"
  );

  return true;
}

bool mpuDataReady() {
  uint8_t status = 0;

  if (
    !mpuReadRegister(
      REG_INT_STATUS,
      status
    )
  ) {
    return false;
  }

  return (status & 0x01) != 0;
}

/*
 * One burst reads all contiguous MPU6050 output registers:
 *
 * 0x3B..0x40  accelerometer
 * 0x41..0x42  temperature
 * 0x43..0x48  gyroscope
 */
bool readAccelGyroRaw(
  int16_t &ax,
  int16_t &ay,
  int16_t &az,
  int16_t &gx,
  int16_t &gy,
  int16_t &gz
) {
  uint8_t data[14];

  if (
    !mpuReadBurst(
      REG_ACCEL_XOUT_H,
      data,
      sizeof(data)
    )
  ) {
    return false;
  }

  ax =
    (int16_t)(
      ((uint16_t)data[0] << 8) |
      data[1]
    );

  ay =
    (int16_t)(
      ((uint16_t)data[2] << 8) |
      data[3]
    );

  az =
    (int16_t)(
      ((uint16_t)data[4] << 8) |
      data[5]
    );

  gx =
    (int16_t)(
      ((uint16_t)data[8] << 8) |
      data[9]
    );

  gy =
    (int16_t)(
      ((uint16_t)data[10] << 8) |
      data[11]
    );

  gz =
    (int16_t)(
      ((uint16_t)data[12] << 8) |
      data[13]
    );

  return true;
}

bool readAccelGyro(
  float &ax,
  float &ay,
  float &az,
  float &gx,
  float &gy,
  float &gz
) {
  int16_t rawAx;
  int16_t rawAy;
  int16_t rawAz;

  int16_t rawGx;
  int16_t rawGy;
  int16_t rawGz;

  if (
    !readAccelGyroRaw(
      rawAx,
      rawAy,
      rawAz,
      rawGx,
      rawGy,
      rawGz
    )
  ) {
    return false;
  }

  float accSensitivity =
    accelSensitivityLSBPerG();

  float gyroSensitivity =
    gyroSensitivityLSBPerDps();

  ax = rawAx / accSensitivity;
  ay = rawAy / accSensitivity;
  az = rawAz / accSensitivity;

  gx = rawGx / gyroSensitivity;
  gy = rawGy / gyroSensitivity;
  gz = rawGz / gyroSensitivity;

  return true;
}

// =============================================================================
// TIMESTAMP
// =============================================================================

void setTimestamp(uint32_t timestamp) {
  initTimestamp = timestamp;
  baseMillis = millis();
}

uint32_t updateCurrentTimestamp() {
  uint32_t elapsedMillis =
    millis() - baseMillis;

  return
    initTimestamp +
    (elapsedMillis / 1000UL);
}

// =============================================================================
// FEATURE PIPELINE
// =============================================================================

void resetFeatureFilters() {
  featureFilterAx.reset();
  featureFilterAy.reset();
  featureFilterAz.reset();

  featureFilterGx.reset();
  featureFilterGy.reset();
  featureFilterGz.reset();
}

void freeFeatureBuffers() {
  if (featureAxBuffer) {
    free(featureAxBuffer);
  }

  if (featureAyBuffer) {
    free(featureAyBuffer);
  }

  if (featureAzBuffer) {
    free(featureAzBuffer);
  }

  if (featureGxBuffer) {
    free(featureGxBuffer);
  }

  if (featureGyBuffer) {
    free(featureGyBuffer);
  }

  if (featureGzBuffer) {
    free(featureGzBuffer);
  }

  featureAxBuffer = nullptr;
  featureAyBuffer = nullptr;
  featureAzBuffer = nullptr;

  featureGxBuffer = nullptr;
  featureGyBuffer = nullptr;
  featureGzBuffer = nullptr;

  featureSampleCount = 0;
  featureBuffersReady = false;

  resetFeatureFilters();
}

bool allocateFeatureBuffers(
  uint16_t windowSize
) {
  freeFeatureBuffers();

  size_t bytes =
    (size_t)windowSize *
    sizeof(float);

  featureAxBuffer =
    (float *)malloc(bytes);

  featureAyBuffer =
    (float *)malloc(bytes);

  featureAzBuffer =
    (float *)malloc(bytes);

  featureGxBuffer =
    (float *)malloc(bytes);

  featureGyBuffer =
    (float *)malloc(bytes);

  featureGzBuffer =
    (float *)malloc(bytes);

  if (
    !featureAxBuffer ||
    !featureAyBuffer ||
    !featureAzBuffer ||
    !featureGxBuffer ||
    !featureGyBuffer ||
    !featureGzBuffer
  ) {
    freeFeatureBuffers();

    return false;
  }

  memset(
    featureAxBuffer,
    0,
    bytes
  );

  memset(
    featureAyBuffer,
    0,
    bytes
  );

  memset(
    featureAzBuffer,
    0,
    bytes
  );

  memset(
    featureGxBuffer,
    0,
    bytes
  );

  memset(
    featureGyBuffer,
    0,
    bytes
  );

  memset(
    featureGzBuffer,
    0,
    bytes
  );

  featureBuffersReady = true;

  resetFeatureFilters();

  return true;
}

void shiftFeatureWindow() {
  uint16_t windowSize =
    campaign_settings.window_size;

  uint16_t stepSize =
    campaign_settings.step_size;

  if (stepSize >= windowSize) {
    featureSampleCount = 0;

    return;
  }

  uint16_t retained =
    windowSize - stepSize;

  size_t retainedBytes =
    (size_t)retained *
    sizeof(float);

  size_t shiftBytes =
    (size_t)stepSize *
    sizeof(float);

  memmove(
    featureAxBuffer,
    (uint8_t *)featureAxBuffer + shiftBytes,
    retainedBytes
  );

  memmove(
    featureAyBuffer,
    (uint8_t *)featureAyBuffer + shiftBytes,
    retainedBytes
  );

  memmove(
    featureAzBuffer,
    (uint8_t *)featureAzBuffer + shiftBytes,
    retainedBytes
  );

  memmove(
    featureGxBuffer,
    (uint8_t *)featureGxBuffer + shiftBytes,
    retainedBytes
  );

  memmove(
    featureGyBuffer,
    (uint8_t *)featureGyBuffer + shiftBytes,
    retainedBytes
  );

  memmove(
    featureGzBuffer,
    (uint8_t *)featureGzBuffer + shiftBytes,
    retainedBytes
  );

  featureSampleCount = retained;
}

/*
 * TO ADD / REMOVE FEATURES
 * ------------------------
 * 1) Change FEATURE_COUNT.
 * 2) Modify extractFeatureVector().
 * 3) Add/remove the corresponding outFeatures[index].
 * 4) Update FEATURE_NAMES in Connect_WIFI.py in the same order.
 * 5) If a new sensor is required, extend acquisition and buffers.
 * 6) Re-check the binary packet size.
 */
void extractFeatureVector(
  float *outFeatures
) {
  uint16_t n =
    campaign_settings.window_size;

  double sumAx = 0;
  double sumAy = 0;
  double sumAz = 0;

  double sumGx = 0;
  double sumGy = 0;
  double sumGz = 0;

  double sumAccMag = 0;
  double sumGyroMag = 0;

  float maxAccMag = 0;
  float maxGyroMag = 0;

  float maxAx = featureAxBuffer[0];
  float maxAy = featureAyBuffer[0];
  float maxAz = featureAzBuffer[0];

  float maxGx = featureGxBuffer[0];
  float maxGy = featureGyBuffer[0];
  float maxGz = featureGzBuffer[0];

  for (uint16_t i = 0; i < n; i++) {
    float ax = featureAxBuffer[i];
    float ay = featureAyBuffer[i];
    float az = featureAzBuffer[i];

    float gx = featureGxBuffer[i];
    float gy = featureGyBuffer[i];
    float gz = featureGzBuffer[i];

    sumAx += ax;
    sumAy += ay;
    sumAz += az;

    sumGx += gx;
    sumGy += gy;
    sumGz += gz;

    if (ax > maxAx) {
      maxAx = ax;
    }

    if (ay > maxAy) {
      maxAy = ay;
    }

    if (az > maxAz) {
      maxAz = az;
    }

    if (gx > maxGx) {
      maxGx = gx;
    }

    if (gy > maxGy) {
      maxGy = gy;
    }

    if (gz > maxGz) {
      maxGz = gz;
    }

    float accMag =
      sqrtf(
        ax * ax +
        ay * ay +
        az * az
      );

    float gyroMag =
      sqrtf(
        gx * gx +
        gy * gy +
        gz * gz
      );

    sumAccMag += accMag;
    sumGyroMag += gyroMag;

    if (accMag > maxAccMag) {
      maxAccMag = accMag;
    }

    if (gyroMag > maxGyroMag) {
      maxGyroMag = gyroMag;
    }
  }

  float nf = (float)n;

  float meanAx = sumAx / nf;
  float meanAy = sumAy / nf;
  float meanAz = sumAz / nf;

  float meanGx = sumGx / nf;
  float meanGy = sumGy / nf;
  float meanGz = sumGz / nf;

  float meanAccMag =
    sumAccMag / nf;

  float meanGyroMag =
    sumGyroMag / nf;

  double varAx = 0;
  double varAy = 0;
  double varAz = 0;

  double varGx = 0;
  double varGy = 0;
  double varGz = 0;

  double varAccMag = 0;
  double varGyroMag = 0;

  double dynamicSma = 0;
  double jerkSum = 0;

  float jerkMax = 0;
  float previousAccMag = 0;

  for (uint16_t i = 0; i < n; i++) {
    float ax = featureAxBuffer[i];
    float ay = featureAyBuffer[i];
    float az = featureAzBuffer[i];

    float gx = featureGxBuffer[i];
    float gy = featureGyBuffer[i];
    float gz = featureGzBuffer[i];

    float accMag =
      sqrtf(
        ax * ax +
        ay * ay +
        az * az
      );

    float gyroMag =
      sqrtf(
        gx * gx +
        gy * gy +
        gz * gz
      );

    float dAx = ax - meanAx;
    float dAy = ay - meanAy;
    float dAz = az - meanAz;

    float dGx = gx - meanGx;
    float dGy = gy - meanGy;
    float dGz = gz - meanGz;

    float dAccMag =
      accMag - meanAccMag;

    float dGyroMag =
      gyroMag - meanGyroMag;

    varAx += dAx * dAx;
    varAy += dAy * dAy;
    varAz += dAz * dAz;

    varGx += dGx * dGx;
    varGy += dGy * dGy;
    varGz += dGz * dGz;

    varAccMag +=
      dAccMag * dAccMag;

    varGyroMag +=
      dGyroMag * dGyroMag;

    dynamicSma +=
      fabsf(dAx) +
      fabsf(dAy) +
      fabsf(dAz);

    if (i > 0) {
      float jerk =
        fabsf(
          accMag -
          previousAccMag
        );

      jerkSum += jerk;

      if (jerk > jerkMax) {
        jerkMax = jerk;
      }
    }

    previousAccMag = accMag;
  }

  outFeatures[0] = maxAccMag;
  outFeatures[1] = meanAccMag;
  outFeatures[2] = sqrtf(varAccMag / n);

  outFeatures[3] = maxGyroMag;
  outFeatures[4] = meanGyroMag;
  outFeatures[5] = sqrtf(varGyroMag / n);

  outFeatures[6] = meanAx;
  outFeatures[7] = maxAx;
  outFeatures[8] = sqrtf(varAx / n);

  outFeatures[9] = meanAy;
  outFeatures[10] = maxAy;
  outFeatures[11] = sqrtf(varAy / n);

  outFeatures[12] = meanAz;
  outFeatures[13] = maxAz;
  outFeatures[14] = sqrtf(varAz / n);

  outFeatures[15] = meanGx;
  outFeatures[16] = maxGx;
  outFeatures[17] = sqrtf(varGx / n);

  outFeatures[18] = meanGy;
  outFeatures[19] = maxGy;
  outFeatures[20] = sqrtf(varGy / n);

  outFeatures[21] = meanGz;
  outFeatures[22] = maxGz;
  outFeatures[23] = sqrtf(varGz / n);

  float tiltRatio =
    constrain(
      meanAx /
      (meanAccMag + 0.000001f),
      -1.0f,
      1.0f
    );

  outFeatures[24] =
    acosf(tiltRatio) *
    (180.0f / PI);

  outFeatures[25] =
    dynamicSma / n;

  outFeatures[26] =
    jerkMax;

  outFeatures[27] =
    (n > 1)
      ? jerkSum / (n - 1)
      : 0;
}

bool sendFeatureVector() {
  if (
    !client ||
    !client.connected()
  ) {
    return false;
  }

  featurepacket_t packet;

  extractFeatureVector(
    packet.features
  );

  packet.counter = counter;
  packet.timestamp =
    updateCurrentTimestamp();

  size_t written =
    client.write(
      (uint8_t *)&packet,
      sizeof(packet)
    );

  if (
    written == sizeof(packet)
  ) {
    counter++;

    return true;
  }

  return false;
}

// =============================================================================
// RAW MODE
// =============================================================================

bool sampleAndSendRaw() {
  if (
    !client ||
    !client.connected()
  ) {
    return false;
  }

  if (!mpuDataReady()) {
    return false;
  }

  int16_t ax;
  int16_t ay;
  int16_t az;

  int16_t gx;
  int16_t gy;
  int16_t gz;

  if (
    !readAccelGyroRaw(
      ax,
      ay,
      az,
      gx,
      gy,
      gz
    )
  ) {
    return false;
  }

  datapacket_t packet;

  // Preserve the same RAW binary representation used by the
  // existing WiFi firmware / Python manager.
  packet.ax = (uint16_t)ax;
  packet.ay = (uint16_t)ay;
  packet.az = (uint16_t)az;

  packet.gx = (uint16_t)gx;
  packet.gy = (uint16_t)gy;
  packet.gz = (uint16_t)gz;

  // MPU6050 is a 6-axis IMU.
  packet.mx = 0;
  packet.my = 0;
  packet.mz = 0;

  packet.counter = counter;
  packet.timestamp =
    updateCurrentTimestamp();

  size_t written =
    client.write(
      (uint8_t *)&packet,
      sizeof(packet)
    );

  if (
    written == sizeof(packet)
  ) {
    counter++;

    return true;
  }

  return false;
}

// =============================================================================
// FEATURES MODE SAMPLING
// =============================================================================

bool sampleFeaturesMode() {
  if (!featureBuffersReady) {
    return false;
  }

  if (!mpuDataReady()) {
    return false;
  }

  float ax;
  float ay;
  float az;

  float gx;
  float gy;
  float gz;

  if (
    !readAccelGyro(
      ax,
      ay,
      az,
      gx,
      gy,
      gz
    )
  ) {
    return false;
  }

#if FEATURE_FILTER_ENABLED
  ax = featureFilterAx.process(ax);
  ay = featureFilterAy.process(ay);
  az = featureFilterAz.process(az);

  gx = featureFilterGx.process(gx);
  gy = featureFilterGy.process(gy);
  gz = featureFilterGz.process(gz);
#endif

  uint16_t i =
    featureSampleCount;

  if (
    i >= campaign_settings.window_size
  ) {
    return false;
  }

  featureAxBuffer[i] = ax;
  featureAyBuffer[i] = ay;
  featureAzBuffer[i] = az;

  featureGxBuffer[i] = gx;
  featureGyBuffer[i] = gy;
  featureGzBuffer[i] = gz;

  featureSampleCount++;

  if (
    featureSampleCount >=
    campaign_settings.window_size
  ) {
    sendFeatureVector();
    shiftFeatureWindow();
  }

  return true;
}

// =============================================================================
// COMMAND HELPERS
// =============================================================================

void sendLine(const char *text) {
  if (
    client &&
    client.connected()
  ) {
    client.println(text);
  }
}

void resetCampaignConfiguration() {
  campaignOngoing = false;
  configurationReceived = false;
  timestampReceived = false;

  counter = 0;

  freeFeatureBuffers();
}

bool parseConfiguration(
  String payload,
  int &samplingFrequency,
  bool &raw,
  int &windowSize,
  int &stepSize
) {
  samplingFrequency =
    DEFAULT_SAMPLING_FREQUENCY;

  raw = true;

  windowSize =
    DEFAULT_WINDOW_SIZE;

  stepSize =
    DEFAULT_STEP_SIZE;

  int position = 0;

  while (position < payload.length()) {
    int separator =
      payload.indexOf(
        ',',
        position
      );

    String token =
      (separator == -1)
        ? payload.substring(position)
        : payload.substring(
            position,
            separator
          );

    int equals =
      token.indexOf('=');

    if (equals > 0) {
      String key =
        token.substring(
          0,
          equals
        );

      String value =
        token.substring(
          equals + 1
        );

      key.trim();
      value.trim();

      if (
        key ==
        "sampling_frequency"
      ) {
        samplingFrequency =
          value.toInt();
      }
      else if (
        key ==
        "raw"
      ) {
        raw =
          value.equalsIgnoreCase(
            "true"
          );
      }
      else if (
        key ==
        "window_size"
      ) {
        windowSize =
          value.toInt();
      }
      else if (
        key ==
        "step_size"
      ) {
        stepSize =
          value.toInt();
      }
    }

    if (separator == -1) {
      break;
    }

    position =
      separator + 1;
  }

  if (
    samplingFrequency <= 0 ||
    samplingFrequency >
      MAX_IMU_SAMPLING_FREQUENCY
  ) {
    return false;
  }

  if (
    !raw &&
    (
      windowSize <= 0 ||
      stepSize <= 0 ||
      stepSize > windowSize
    )
  ) {
    return false;
  }

  return true;
}

void handleTimestampMessage(
  String request
) {
  String payload =
    request.substring(10);

  uint32_t timestamp =
    (uint32_t)strtoul(
      payload.c_str(),
      nullptr,
      10
    );

  setTimestamp(timestamp);

  timestampReceived = true;

  Serial.print(
    "[CONFIG] Timestamp: "
  );
  Serial.println(timestamp);
}

void handleConfigurationMessage(
  String request
) {
  String payload =
    request.substring(7);

  int samplingFrequency;
  bool raw;
  int windowSize;
  int stepSize;

  if (
    !parseConfiguration(
      payload,
      samplingFrequency,
      raw,
      windowSize,
      stepSize
    )
  ) {
    sendLine("ERR:CONFIG");

    return;
  }

  if (
    !configureMPU6050(
      samplingFrequency
    )
  ) {
    sendLine("ERR:CONFIG");

    return;
  }

  campaign_settings.sampling_frequency =
    (uint16_t)samplingFrequency;

  campaign_settings.mode =
    raw
      ? CAMPAIGN_RAW
      : CAMPAIGN_FEATURES;

  campaign_settings.window_size =
    (uint16_t)windowSize;

  campaign_settings.step_size =
    (uint16_t)stepSize;

  if (
    campaign_settings.mode ==
    CAMPAIGN_FEATURES
  ) {
    if (
      !allocateFeatureBuffers(
        campaign_settings.window_size
      )
    ) {
      sendLine("ERR:CONFIG");

      return;
    }
  }
  else {
    freeFeatureBuffers();
  }

  counter = 0;

  configurationReceived = true;

  sendLine("OK:CONFIG");
  sendLine("ACK_OK");

  Serial.println(
    "[CONFIG] Campaign configured"
  );

  Serial.print(
    "[CONFIG] Mode: "
  );

  if (
    campaign_settings.mode ==
    CAMPAIGN_RAW
  ) {
    Serial.println("RAW");
  }
  else {
    Serial.println("FEATURES");

    Serial.print(
      "[CONFIG] Window size: "
    );
    Serial.println(
      campaign_settings.window_size
    );

    Serial.print(
      "[CONFIG] Step size: "
    );
    Serial.println(
      campaign_settings.step_size
    );
  }
}

void handleActivityMessage(
  String request
) {
  String payload =
    request.substring(9);

  payload.trim();

  if (
    payload.equalsIgnoreCase(
      "START"
    )
  ) {
    if (
      !timestampReceived ||
      !configurationReceived
    ) {
      Serial.println(
        "[WARN] START received before complete configuration"
      );
    }

    campaignOngoing = true;

    reconnectTimerActive = false;

    Serial.println(
      "[ACTIVITY] START"
    );
  }
  else if (
    payload.equalsIgnoreCase(
      "STOP"
    )
  ) {
    campaignOngoing = false;

    freeFeatureBuffers();

    Serial.println(
      "[ACTIVITY] STOP"
    );
  }
  else {
    Serial.println(
      "[WARN] Invalid ACTIVITY command"
    );
  }
}

void handleWiFiCommand() {
  if (
    !client ||
    !client.connected() ||
    !client.available()
  ) {
    return;
  }

  String request =
    client.readStringUntil('\n');

  request.trim();

  if (
    request.length() == 0
  ) {
    return;
  }

  Serial.print("[RX] ");
  Serial.println(request);

  if (
    request.equalsIgnoreCase(
      "PING"
    )
  ) {
    sendLine("PONG");
  }
  else if (
    request.equalsIgnoreCase(
      "HELLO"
    )
  ) {
    String hello =
      "HELLO FROM " + imu_id +
      " ESP32-C3 MPU6050";

    sendLine(
      hello.c_str()
    );
  }
  else if (
    request.equalsIgnoreCase(
      "BYE"
    )
  ) {
    sendLine("GOODBYE");
    client.stop();
  }
  else if (
    request.equalsIgnoreCase(
      "BOOT_ID"
    )
  ) {
    client.println(boot_id);
  }
  else if (
    request.equalsIgnoreCase(
      "BATTERY"
    )
  ) {
    // ESP32-C3 Super Mini has no integrated battery monitor.
    sendLine("BATTERY:NA");
  }
  else if (
    request.startsWith(
      "TIMESTAMP:"
    )
  ) {
    handleTimestampMessage(
      request
    );
  }
  else if (
    request.startsWith(
      "CONFIG:"
    )
  ) {
    handleConfigurationMessage(
      request
    );
  }
  else if (
    request.startsWith(
      "ACTIVITY:"
    )
  ) {
    handleActivityMessage(
      request
    );
  }
  else {
    sendLine("UNKNOWN COMMAND");
  }
}

// =============================================================================
// WIFI
// =============================================================================

String buildImuIdFromMac(String macAddress) {
  // MAC format expected from WiFi.macAddress():
  // AA:BB:CC:DD:EE:FF
  macAddress.replace(":", "");
  macAddress.toUpperCase();

  if (macAddress.length() >= 4) {
    return "IMU" + macAddress.substring(macAddress.length() - 4);
  }

  return "IMU_UNKNOWN";
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);

  WiFi.setSleep(false);

  // Read station MAC and derive a short IMU identifier.
  String macAddress = WiFi.macAddress();
  imu_id = buildImuIdFromMac(macAddress);

  // Expose the same identifier as WiFi hostname.
  WiFi.setHostname(imu_id.c_str());

  Serial.println();
  Serial.println(
    "============================================"
  );
  Serial.print("[DEVICE] IMU ID: ");
  Serial.println(imu_id);
  Serial.print("[DEVICE] MAC:    ");
  Serial.println(macAddress);
  Serial.println(
    "============================================"
  );

  Serial.print(
    "[WIFI] Connecting to "
  );
  Serial.println(WIFI_SSID);

  WiFi.begin(
    WIFI_SSID,
    WIFI_PASSWORD
  );

  while (
    WiFi.status() != WL_CONNECTED
  ) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();

  Serial.println(
    "[WIFI] Connected"
  );

  Serial.print(
    "[WIFI] IMU ID: "
  );
  Serial.println(
    imu_id
  );

  Serial.print(
    "[WIFI] IP: "
  );
  Serial.println(
    WiFi.localIP()
  );

  Serial.print(
    "[WIFI] MAC: "
  );
  Serial.println(
    WiFi.macAddress()
  );

  // Disable Nagle to reduce latency for small binary packets.
  server.begin();
  server.setNoDelay(true);

  Serial.print(
    "[WIFI] TCP server listening on port "
  );
  Serial.println(TCP_PORT);
}

void acceptClientIfNeeded() {
  if (
    client &&
    client.connected()
  ) {
    return;
  }

  WiFiClient newClient =
    server.available();

  if (!newClient) {
    return;
  }

  client = newClient;
  client.setNoDelay(true);
  client.setTimeout(100);

  Serial.print(
    "[WIFI] TCP client connected: "
  );
  Serial.println(
    client.remoteIP()
  );

  reconnectTimerActive = false;
}

// =============================================================================
// SETUP
// =============================================================================

void setup() {
  Serial.begin(115200);

  delay(1500);

  Serial.println();
  Serial.println(
    "============================================"
  );
  Serial.println(
    "ESP32-C3 + MPU6050 WiFi RAW/FEATURES"
  );
  Serial.println(
    "============================================"
  );

  Wire.begin(
    SDA_PIN,
    SCL_PIN
  );

  Wire.setClock(400000);

  if (!mpuDevicePresent()) {
    Serial.println(
      "[ERROR] MPU6050 not found at 0x68"
    );

    while (true) {
      delay(1000);
    }
  }

  uint8_t whoAmI = 0;

  if (
    !mpuReadRegister(
      REG_WHO_AM_I,
      whoAmI
    ) ||
    whoAmI != 0x68
  ) {
    Serial.print(
      "[ERROR] Invalid WHO_AM_I: 0x"
    );
    Serial.println(
      whoAmI,
      HEX
    );

    while (true) {
      delay(1000);
    }
  }

  Serial.println(
    "[IMU] MPU6050 detected"
  );

  // Initial configuration.
  if (
    !configureMPU6050(
      DEFAULT_SAMPLING_FREQUENCY
    )
  ) {
    Serial.println(
      "[ERROR] Initial MPU6050 configuration failed"
    );

    while (true) {
      delay(1000);
    }
  }

  // Changes every physical reboot.
  boot_id = esp_random();

  if (boot_id == 0) {
    boot_id = 1;
  }

  Serial.print(
    "[BOOT] boot_id="
  );
  Serial.println(boot_id);

  connectWiFi();
}

// =============================================================================
// LOOP
// =============================================================================

void loop() {
  if (
    WiFi.status() != WL_CONNECTED
  ) {
    Serial.println(
      "[WIFI] Connection lost. Reconnecting..."
    );

    client.stop();

    connectWiFi();

    return;
  }

  acceptClientIfNeeded();

  bool isConnected =
    client &&
    client.connected();

  if (
    !isConnected &&
    campaignOngoing &&
    !reconnectTimerActive
  ) {
    disconnectStartMs = millis();
    reconnectTimerActive = true;

    Serial.println(
      "[WIFI] Client disconnected during campaign"
    );
  }

  if (isConnected) {
    handleWiFiCommand();

    reconnectTimerActive = false;

    if (campaignOngoing) {
      if (
        campaign_settings.mode ==
        CAMPAIGN_RAW
      ) {
        sampleAndSendRaw();
      }
      else if (
        campaign_settings.mode ==
        CAMPAIGN_FEATURES
      ) {
        sampleFeaturesMode();
      }
    }
  }
  else if (
    campaignOngoing &&
    reconnectTimerActive
  ) {
    if (
      millis() -
      disconnectStartMs >
      RECONNECT_TIMEOUT_MS
    ) {
      Serial.println(
        "[WIFI] Reconnect timeout. Campaign aborted."
      );

      campaignOngoing = false;
      reconnectTimerActive = false;

      freeFeatureBuffers();
    }
  }

  // Yield to the ESP32 networking stack without imposing a sampling period.
  delay(0);
}
