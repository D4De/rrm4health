/* Select board Nano 33 BLE sense REV 2 nRF52840 */

#include "Arduino_BMI270_BMM150_AAAC.h"
#include <ArduinoBLE.h>
#include <TimeLib.h>

#define IMU_DEFAULT_NAME  "IMUXXXX"
typedef volatile uint32_t REG32;
#define pREG32 (REG32 *)
#define MAC_ADDRESS_HIGH  (*(pREG32 (0x100000a8)))
#define MAC_ADDRESS_LOW   (*(pREG32 (0x100000a4)))

/* Nano 33 BLE sense */
/* Analog pin used to read battery voltage (through voltage divider) */
#define BATTERY_PIN                           A0
#define USB_VOLTAGE_PIN                       A6
#define USB_THRESHOLD                         4.5
enum PowerSource {
  POWER_USB,
  POWER_BATTERY,
  POWER_UNKNOWN
};

// Voltage reference and divider settings
#define ADC_REF_VOLTAGE                       3.3      // 3.3V reference on Nano 33 BLE Sense
#define ADC_RESOLUTION                        1023        // 10-bit ADC
#define VOLTAGE_DIVIDER_RATIO                 2.0 // Adjust if using a different divider

#define ACK_OK                                0x00
#define ACK_KO                                0xFF

#define TIMESTAMP_HEX_LEN                     4 /* 8 nibbles packed into 4 bytes */
#define CONFIGURATION_HEX_LEN                 6 /* freq(1) + mode(1) + window_size(2) + step_size(2) */
#define ACTIVITY_HEX_LEN                      2 /* START or STOP */
#define BATTLEVEL_HEX_LEN                     2 /* START or STOP */

#define START_CAMPAIGN                        0x00
#define STOP_CAMPAIGN                         0x0F
#define CAMPAIGN_RAW                          0x00
#define CAMPAIGN_FEATURES                     0x01
#define CAMPAIGN_QUAT                         0x0F

#define DEFAULT_COUNTER_INIT                  0
#define DEFAULT_SAMPLING_FREQUENCY            10 /* 10 Hz - 10 samples in a second */
#define MAX_IMU_SAMPLING_FREQUENCY            100 /* BMI270 ACC/GYRO configured at 100 Hz */
#define DEFAULT_TIMESTAMP_INIT                0

#define SAMPL_FREQ_ADJ                        0.5  /* the sampling is not precise ... */
#define BATTERY_SAMPLING_FREQUENCY            10000 /* 30 seconds */

#define MSG_TS                                0
#define MSG_CAMP                              1
#define MSG_ACK                               1
#define REQ_MSG                               3 /* timestamp, campaign configuration, ack */

//For reconnection
#define RECONNECT_TIMEOUT_MS                  30000  // 30 seconds

/* typedefs */

typedef struct {
  float x, y, z;
} sensor_data_t;

typedef struct _datapacket {  /* 3 x 2 x 3 bytes + 2 bytes + 2 bytes + 4 bytes = 26 */
  int16_t ax, ay, az;  /* raw values */
  int16_t gx, gy, gz;
  int16_t mx, my, mz;
  uint16_t counter;
  uint32_t timestamp;
} datapacket_t;

typedef struct _datapacket_quat {  /* 4 x 4 bytes + 2 bytes + 4 bytes = 22 */
  uint32_t q0, q1, q2, q3;  /* aggregated values */
  uint16_t counter;
  uint32_t timestamp;
} datapacket_quat_t;

#define FEATURE_COUNT 28

/*
 * FEATURES packet:
 * 28 float32 features + uint16 counter + uint32 timestamp = 118 bytes.
 * The order of features must match FEATURE_NAMES in the Python manager.
 */
typedef struct __attribute__((packed)) _featurepacket {
  float features[FEATURE_COUNT];
  uint16_t counter;
  uint32_t timestamp;
} featurepacket_t;

static_assert(sizeof(featurepacket_t) == 118,
              "Unexpected featurepacket_t size");

typedef struct _campaignpar {
  uint8_t   sampling_frequency; /* requested internal sampling frequency */
  uint16_t  interval;           /* RAW-mode legacy delay in ms */
  uint8_t   mode;               /* RAW / FEATURES / QUAT */
  uint16_t  window_size;        /* preprocessing window in samples */
  uint16_t  step_size;          /* new samples between feature vectors */
} campaign_parameters_t;

typedef struct _timestamp_data {
  uint8_t yy, mm, dd, HH, MM, SS;
  uint16_t cents;
} timestamp_data_t;

typedef enum {
  STATE_POWER_ON            = 0,
  STATE_WAIT_TIMESTAMP      = 1,
  STATE_WAIT_CONFIGURATION  = 2,
  STATE_SEND_ACK            = 3,
  STATE_READY               = 4,
  STATE_ACQUISITION         = 5,
  STATE_DISCONNECTION       = 6,
  STATE_STOP                = 7,
  STATE_SLEEP               = 8,
  STATE_ZOMBIE              = 9
} imu_states_t;

#define AAAC_KIT_UUID(val)    ("555a0002-" val "-467a-9538-01f0652c74e8")

#define UUID_SRV              AAAC_KIT_UUID("0000")
#define UUID_CHR_ACK          "555a0002-0010-467a-9538-01f0652c74e8"  //AAAC_KIT_UUID("0010")
#define UUID_CHR_SENSOR       "555a0002-0030-467a-9538-01f0652c74e8"  //AAAC_KIT_UUID("0030")
#define UUID_CHR_QUAT         "555a0002-0031-467a-9538-01f0652c74e8"  //AAAC_KIT_UUID("0031")
#define UUID_CHR_FEATURES     "555a0002-0032-467a-9538-01f0652c74e8"
#define UUID_CHR_TIMEST       "555a0002-0034-467a-9538-01f0652c74e8"
#define UUID_CHR_CAMPCONF     "555a0002-0035-467a-9538-01f0652c74e8"
#define UUID_CHR_ACTIVITY     "555a0002-0040-467a-9538-01f0652c74e8"
#define UUID_BATTERY_SRV      "0000180F-0000-1000-8000-00805F9B34FB" //"180F" //
#define UUID_NOTIFY_BATTERY   "00002A19-0000-1000-8000-00805F9B34FB" //"2A19" //

//For reconnection
#define BOOT_ID_UUID "555A0002-0099-467A-9538-01F0652C74E8"

// Define BLE service and characteristic
BLEService        bleService                  (UUID_SRV);
BLECharacteristic ackCharacteristic           (UUID_CHR_ACK, BLERead, MSG_ACK);		
BLECharacteristic sensorsCharacteristic       (UUID_CHR_SENSOR, BLENotify, sizeof(datapacket_t));		
BLECharacteristic quatCharacteristic          (UUID_CHR_QUAT, BLENotify, sizeof(datapacket_t));
BLECharacteristic featuresCharacteristic      (UUID_CHR_FEATURES, BLENotify, sizeof(featurepacket_t)); 		
BLECharacteristic timestampCharacteristic     (UUID_CHR_TIMEST, BLEWrite, TIMESTAMP_HEX_LEN);
BLECharacteristic campaignCharacteristic      (UUID_CHR_CAMPCONF, BLEWrite, CONFIGURATION_HEX_LEN);		
BLECharacteristic activityCharacteristic      (UUID_CHR_ACTIVITY, BLEWrite, ACTIVITY_HEX_LEN);	/* start and stop */	
BLEService        bleBatteryService           (UUID_BATTERY_SRV);
BLECharacteristic batteryLevelCharacteristic  (UUID_NOTIFY_BATTERY, BLERead | BLENotify, BATTLEVEL_HEX_LEN);		
//BLEUnsignedCharCharacteristic batteryLevelChar(UUID_BATTERY, BLERead | BLENotify);

//For reconnection
BLEUnsignedIntCharacteristic bootIdChar(BOOT_ID_UUID, BLERead);

/* SENSOR */
sensor_data_t acc, gyr;
const float accelerationThreshold = 2.5; // threshold of significant in G's

volatile imu_states_t                         imu_state;
campaign_parameters_t                         campaign_settings;
uint16_t                                      counter;
unsigned long                                 presentTS;      /* present time stamp */
unsigned long                                 initTimestamp;  /* initial time stamp sent from client */
unsigned long                                 baseMillis;     /* millis at the time of setting initTimestamp */

timestamp_data_t                              ts;

uint8_t                                       payload_size = sizeof(datapacket_t);

volatile bool                                 exchanged_msg[REQ_MSG]; 
volatile bool                                 blnStart;
volatile bool                                 blnStop;
volatile bool                                 campaign_ongoing;
bool                                          batteryPowered;

//For reconnection
unsigned long disconnectStartTime = 0;
uint32_t boot_id;

uint64_t getDeviceID() {
  return ((uint64_t)NRF_FICR->DEVICEID[1] << 32) |
          NRF_FICR->DEVICEID[0];
}


/* =========================================================================
 * GENERIC ON-DEVICE FEATURE PREPROCESSING
 *
 * Current feature set (same order as the Python manager):
 *
 *  0 acc_mag_max       1 acc_mag_mean       2 acc_mag_std
 *  3 gyro_mag_max      4 gyro_mag_mean      5 gyro_mag_std
 *  6 ax_mean           7 ax_max             8 ax_std
 *  9 ay_mean          10 ay_max            11 ay_std
 * 12 az_mean          13 az_max            14 az_std
 * 15 gx_mean          16 gx_max            17 gx_std
 * 18 gy_mean          19 gy_max            20 gy_std
 * 21 gz_mean          22 gz_max            23 gz_std
 * 24 tilt
 * 25 dynamic_sma      26 jerk_max           27 jerk_mean
 *
 * HOW TO ADD/REMOVE FEATURES FOR ANOTHER APPLICATION
 * --------------------------------------------------
 * 1. Change FEATURE_COUNT above.
 * 2. Add/remove the computation in extractFeatureVector().
 * 3. Store each feature in outFeatures[index].
 * 4. Keep the exact same order in FEATURE_NAMES in the Python manager.
 *    FEATURE_COUNT / packet length / struct format in Python are derived from
 *    that list and must not be edited manually.
 * 5. If a new feature needs another sensor (e.g. magnetometer), extend the
 *    buffers, allocation/free logic, shiftFeatureWindow() and sampling code.
 * 6. Re-check BLE packet size whenever FEATURE_COUNT changes.
 *
 * HARDWARE NOTE - NANO 33 BLE SENSE REV2
 * --------------------------------------
 * BMI270 accelerometer and gyroscope are configured at 100 Hz. This firmware
 * uses the optimized readAccelGyro() method so ACC+GYRO are fetched with one
 * bmi2_get_sensor_data() call per sample. BMM150 is not read in FEATURES mode
 * because the current 28-feature set does not use magnetometer data.
 * ========================================================================= */

#define FEATURE_FILTER_ENABLED 1

const float FEATURE_B0 = 0.04613188f;
const float FEATURE_B1 = 0.09226376f;
const float FEATURE_B2 = 0.04613188f;
const float FEATURE_A1 = -1.30728503f;
const float FEATURE_A2 = 0.49181255f;

class FeatureBiquadFilter {
  private:
    float x1, x2, y1, y2;

  public:
    FeatureBiquadFilter() { reset(); }

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

float* featureAxBuffer = NULL;
float* featureAyBuffer = NULL;
float* featureAzBuffer = NULL;
float* featureGxBuffer = NULL;
float* featureGyBuffer = NULL;
float* featureGzBuffer = NULL;

uint16_t featureSampleCount = 0;
uint32_t featureLastSampleUs = 0;
bool featureBuffersReady = false;

void resetFeatureFilters() {
  featureFilterAx.reset();
  featureFilterAy.reset();
  featureFilterAz.reset();
  featureFilterGx.reset();
  featureFilterGy.reset();
  featureFilterGz.reset();
}

void freeFeatureBuffers() {
  if (featureAxBuffer) free(featureAxBuffer);
  if (featureAyBuffer) free(featureAyBuffer);
  if (featureAzBuffer) free(featureAzBuffer);
  if (featureGxBuffer) free(featureGxBuffer);
  if (featureGyBuffer) free(featureGyBuffer);
  if (featureGzBuffer) free(featureGzBuffer);

  featureAxBuffer = featureAyBuffer = featureAzBuffer = NULL;
  featureGxBuffer = featureGyBuffer = featureGzBuffer = NULL;

  featureSampleCount = 0;
  featureLastSampleUs = 0;
  featureBuffersReady = false;
}

bool allocateFeatureBuffers(uint16_t windowSize) {
  freeFeatureBuffers();

  if (windowSize == 0)
    return false;

  size_t bytes = (size_t)windowSize * sizeof(float);

  featureAxBuffer = (float*)malloc(bytes);
  featureAyBuffer = (float*)malloc(bytes);
  featureAzBuffer = (float*)malloc(bytes);
  featureGxBuffer = (float*)malloc(bytes);
  featureGyBuffer = (float*)malloc(bytes);
  featureGzBuffer = (float*)malloc(bytes);

  if (!featureAxBuffer || !featureAyBuffer || !featureAzBuffer ||
      !featureGxBuffer || !featureGyBuffer || !featureGzBuffer) {
    Serial.println("[FEATURES] Buffer allocation failed");
    freeFeatureBuffers();
    return false;
  }

  memset(featureAxBuffer, 0, bytes);
  memset(featureAyBuffer, 0, bytes);
  memset(featureAzBuffer, 0, bytes);
  memset(featureGxBuffer, 0, bytes);
  memset(featureGyBuffer, 0, bytes);
  memset(featureGzBuffer, 0, bytes);

  featureSampleCount = 0;
  featureLastSampleUs = 0;
  featureBuffersReady = true;
  resetFeatureFilters();

  Serial.print("[FEATURES] Buffers allocated. Window=");
  Serial.print(windowSize);
  Serial.print(", RAM=");
  Serial.print(bytes * 6);
  Serial.println(" bytes");

  return true;
}

void shiftFeatureWindow() {
  uint16_t windowSize = campaign_settings.window_size;
  uint16_t stepSize = campaign_settings.step_size;

  if (stepSize >= windowSize) {
    featureSampleCount = 0;
    return;
  }

  uint16_t retained = windowSize - stepSize;
  size_t retainedBytes = (size_t)retained * sizeof(float);
  size_t shiftBytes = (size_t)stepSize * sizeof(float);

  memmove(featureAxBuffer, (uint8_t*)featureAxBuffer + shiftBytes, retainedBytes);
  memmove(featureAyBuffer, (uint8_t*)featureAyBuffer + shiftBytes, retainedBytes);
  memmove(featureAzBuffer, (uint8_t*)featureAzBuffer + shiftBytes, retainedBytes);
  memmove(featureGxBuffer, (uint8_t*)featureGxBuffer + shiftBytes, retainedBytes);
  memmove(featureGyBuffer, (uint8_t*)featureGyBuffer + shiftBytes, retainedBytes);
  memmove(featureGzBuffer, (uint8_t*)featureGzBuffer + shiftBytes, retainedBytes);

  featureSampleCount = retained;
}

void extractFeatureVector(float* outFeatures) {
  const uint16_t n = campaign_settings.window_size;

  double sumAx = 0.0, sumAy = 0.0, sumAz = 0.0;
  double sumGx = 0.0, sumGy = 0.0, sumGz = 0.0;
  double sumAccMag = 0.0, sumGyroMag = 0.0;

  float maxAx = featureAxBuffer[0];
  float maxAy = featureAyBuffer[0];
  float maxAz = featureAzBuffer[0];
  float maxGx = featureGxBuffer[0];
  float maxGy = featureGyBuffer[0];
  float maxGz = featureGzBuffer[0];
  float maxAccMag = 0.0f;
  float maxGyroMag = 0.0f;

  for (uint16_t i = 0; i < n; i++) {
    float ax = featureAxBuffer[i];
    float ay = featureAyBuffer[i];
    float az = featureAzBuffer[i];
    float gx = featureGxBuffer[i];
    float gy = featureGyBuffer[i];
    float gz = featureGzBuffer[i];

    sumAx += ax; sumAy += ay; sumAz += az;
    sumGx += gx; sumGy += gy; sumGz += gz;

    if (ax > maxAx) maxAx = ax;
    if (ay > maxAy) maxAy = ay;
    if (az > maxAz) maxAz = az;
    if (gx > maxGx) maxGx = gx;
    if (gy > maxGy) maxGy = gy;
    if (gz > maxGz) maxGz = gz;

    float accMag = sqrtf(ax * ax + ay * ay + az * az);
    float gyroMag = sqrtf(gx * gx + gy * gy + gz * gz);

    sumAccMag += accMag;
    sumGyroMag += gyroMag;

    if (accMag > maxAccMag) maxAccMag = accMag;
    if (gyroMag > maxGyroMag) maxGyroMag = gyroMag;
  }

  float meanAx = (float)(sumAx / n);
  float meanAy = (float)(sumAy / n);
  float meanAz = (float)(sumAz / n);
  float meanGx = (float)(sumGx / n);
  float meanGy = (float)(sumGy / n);
  float meanGz = (float)(sumGz / n);
  float meanAccMag = (float)(sumAccMag / n);
  float meanGyroMag = (float)(sumGyroMag / n);

  double varAx = 0.0, varAy = 0.0, varAz = 0.0;
  double varGx = 0.0, varGy = 0.0, varGz = 0.0;
  double varAccMag = 0.0, varGyroMag = 0.0;
  double dynamicSmaSum = 0.0;
  double jerkSum = 0.0;
  float jerkMax = 0.0f;
  float previousAccMag = 0.0f;

  for (uint16_t i = 0; i < n; i++) {
    float ax = featureAxBuffer[i];
    float ay = featureAyBuffer[i];
    float az = featureAzBuffer[i];
    float gx = featureGxBuffer[i];
    float gy = featureGyBuffer[i];
    float gz = featureGzBuffer[i];

    float accMag = sqrtf(ax * ax + ay * ay + az * az);
    float gyroMag = sqrtf(gx * gx + gy * gy + gz * gz);

    float dAx = ax - meanAx;
    float dAy = ay - meanAy;
    float dAz = az - meanAz;
    float dGx = gx - meanGx;
    float dGy = gy - meanGy;
    float dGz = gz - meanGz;
    float dAccMag = accMag - meanAccMag;
    float dGyroMag = gyroMag - meanGyroMag;

    varAx += dAx * dAx;
    varAy += dAy * dAy;
    varAz += dAz * dAz;
    varGx += dGx * dGx;
    varGy += dGy * dGy;
    varGz += dGz * dGz;
    varAccMag += dAccMag * dAccMag;
    varGyroMag += dGyroMag * dGyroMag;

    dynamicSmaSum += fabsf(dAx) + fabsf(dAy) + fabsf(dAz);

    if (i > 0) {
      float jerk = fabsf(accMag - previousAccMag);
      jerkSum += jerk;
      if (jerk > jerkMax) jerkMax = jerk;
    }
    previousAccMag = accMag;
  }

  outFeatures[0] = maxAccMag;
  outFeatures[1] = meanAccMag;
  outFeatures[2] = sqrtf((float)(varAccMag / n));

  outFeatures[3] = maxGyroMag;
  outFeatures[4] = meanGyroMag;
  outFeatures[5] = sqrtf((float)(varGyroMag / n));

  outFeatures[6] = meanAx;
  outFeatures[7] = maxAx;
  outFeatures[8] = sqrtf((float)(varAx / n));

  outFeatures[9] = meanAy;
  outFeatures[10] = maxAy;
  outFeatures[11] = sqrtf((float)(varAy / n));

  outFeatures[12] = meanAz;
  outFeatures[13] = maxAz;
  outFeatures[14] = sqrtf((float)(varAz / n));

  outFeatures[15] = meanGx;
  outFeatures[16] = maxGx;
  outFeatures[17] = sqrtf((float)(varGx / n));

  outFeatures[18] = meanGy;
  outFeatures[19] = maxGy;
  outFeatures[20] = sqrtf((float)(varGy / n));

  outFeatures[21] = meanGz;
  outFeatures[22] = maxGz;
  outFeatures[23] = sqrtf((float)(varGz / n));

  float tiltRatio = meanAx / (meanAccMag + 0.000001f);
  tiltRatio = constrain(tiltRatio, -1.0f, 1.0f);
  float tilt = acosf(tiltRatio) * (180.0f / PI);

  outFeatures[24] = tilt;
  outFeatures[25] = (float)(dynamicSmaSum / n);
  outFeatures[26] = jerkMax;
  outFeatures[27] =
      n > 1 ? (float)(jerkSum / (n - 1)) : 0.0f;
}

bool sendFeatureVector() {
  featurepacket_t packet;
  extractFeatureVector(packet.features);

  packet.counter = counter;
  packet.timestamp = updateCurrentTimestamp();

  bool ok = featuresCharacteristic.writeValue(
      (uint8_t*)&packet,
      sizeof(packet),
      false
  );

  if (ok) {
    Serial.print("[FEATURES] Sent vector nth=");
    Serial.println(counter);
  } else {
    Serial.print("[FEATURES] BLE write failed nth=");
    Serial.println(counter);
  }

  counter++;
  return ok;
}

void sampleFeaturesMode() {
  if (!featureBuffersReady)
    return;

  uint32_t nowUs = micros();
  uint32_t periodUs =
      1000000UL / campaign_settings.sampling_frequency;

  if (featureLastSampleUs != 0 &&
      (uint32_t)(nowUs - featureLastSampleUs) < periodUs) {
    return;
  }

  if (featureLastSampleUs == 0)
    featureLastSampleUs = nowUs;
  else
    featureLastSampleUs += periodUs;

  if ((uint32_t)(nowUs - featureLastSampleUs) > (periodUs * 2UL))
    featureLastSampleUs = nowUs;

  float ax, ay, az;
  float gx, gy, gz;

  /*
   * Hardware-optimized BMI270 read:
   * one sensor API access returns both ACC and GYRO.
   */
  if (!IMU.readAccelGyro(ax, ay, az, gx, gy, gz))
    return;

#if FEATURE_FILTER_ENABLED
  ax = featureFilterAx.process(ax);
  ay = featureFilterAy.process(ay);
  az = featureFilterAz.process(az);
  gx = featureFilterGx.process(gx);
  gy = featureFilterGy.process(gy);
  gz = featureFilterGz.process(gz);
#endif

  uint16_t index = featureSampleCount;

  featureAxBuffer[index] = ax;
  featureAyBuffer[index] = ay;
  featureAzBuffer[index] = az;
  featureGxBuffer[index] = gx;
  featureGyBuffer[index] = gy;
  featureGzBuffer[index] = gz;

  featureSampleCount++;

  if (featureSampleCount >= campaign_settings.window_size) {
    sendFeatureVector();
    shiftFeatureWindow();
  }
}


void setup() {
  uint8_t i;
  char ble_name[8] = IMU_DEFAULT_NAME; // Null-terminated string must be 1 longer than you set it, for the null
  digitalToggle(LED_BLUE);
  delay(1000);
  digitalToggle(LED_BLUE);

  Serial.begin(115200);
//  while (!Serial);
  Serial.println("IMU alive");
  Serial.println("---------\n");

  /* */
  pinMode(BATTERY_PIN, INPUT);
  pinMode(USB_VOLTAGE_PIN, INPUT);
  analogReference(AR_VDD);

  /* setting up the sensors */
  while(!setupSensors())
  {
    ; /* nothing to do if there are no sensors */
  }

  digitalToggle(LED_RED);
  delay(1000);
  digitalToggle(LED_RED);
  delay(2000);  /* two seconds to blink */

  // Initialize BLE
  BLE.begin();
  uint32_t addr_low  = MAC_ADDRESS_LOW;
  byte_to_str(&ble_name[3], (addr_low >> 8) & 0xFF);
  byte_to_str(&ble_name[5], addr_low & 0xFF);
  BLE.setLocalName(ble_name);
  BLE.setDeviceName(ble_name);
/*
  Bluefruit.setTxPower(4);    // Check bluefruit.h for supported values
  Bluefruit.autoConnLed(false);
  Bluefruit.configPrphBandwidth(31);
*/
  digitalToggle(LED_BLUE);
  delay(1000);
  digitalToggle(LED_BLUE);
  delay(1000);

  // assign event handlers for connected, disconnected to peripheral
  //BLE.setEventHandler(BLEConnected, connect_callback);
  //BLE.setEventHandler(BLEDisconnected, disconnect_callback);

  /* check if battery powered */
  PowerSource source = detectPowerSource();
  if (source == POWER_BATTERY){
     Serial.println("Battery powered");
     batteryPowered = true;
  } else {
     Serial.println("Not Battery powered");
     batteryPowered = false;
  }
  float usbVoltage = readUSBVoltage();
  float vccVoltage = readVCCVoltage();
  
  Serial.print("USB Voltage: ");
  Serial.print(usbVoltage, 2);
  Serial.println("V");
  
  Serial.print("VCC Voltage: ");
  Serial.print(vccVoltage, 2);
  Serial.println("V");

  startBLEandConfigure();
  setWriteHandlers();
  Serial.println("BLE up and configured");

  Serial.print("IMU ");
  Serial.print(ble_name);
  Serial.println(" alive");

  // Start advertising
  startAdv();
  Serial.println("Advertising started");

  /* defaults */
  counter = DEFAULT_COUNTER_INIT;
  initTimestamp = DEFAULT_TIMESTAMP_INIT;

  for(i = 0; i < REQ_MSG; i++)
    exchanged_msg[i] = false;
  campaign_ongoing = false;
  blnStart = false;
  blnStop = false;
  imu_state = STATE_POWER_ON;
}

volatile bool firsttime = true;
bool changestate = false;
bool everConnected = false;
bool unexDisconnected = false;
static unsigned long lastSampleTime = 0;

void loop() {
  BLEDevice dataHub = BLE.central();
  static uint16_t step = 0;

  if(firsttime){
    print_state();
    firsttime = false;
  }
  if(imu_state == STATE_POWER_ON)
    everConnected = false;
  step++;

  switch(imu_state){
    case STATE_POWER_ON: 
    case STATE_WAIT_TIMESTAMP:
      if(exchanged_msg[MSG_TS])
		    imu_state = STATE_WAIT_CONFIGURATION;
      break;
    case STATE_READY:
      if(blnStart){
        imu_state = STATE_ACQUISITION;
        blnStart = false;
      } else if(!dataHub.connected()){
        Serial.println(" Unexpected disconnect. Moving to POWER_ON.");
        imu_state = STATE_POWER_ON;
        everConnected = true;
        changestate = true;  
      } 
      break;
    case STATE_SLEEP: /* waiting for disconnection or new campaign */
      if(!dataHub.connected()){
        Serial.println(" Campaign concluded. Moving to POWER_ON for another campaign");
        imu_state = STATE_POWER_ON;
        everConnected = false;
        changestate = true;  
      } else {
        delay(1000);
      }
      break;
    case STATE_SEND_ACK:
      if(dataHub.connected()){
        sendACK_OK();
        imu_state = STATE_READY;
        delay(1000);
      }
      break;
    case STATE_WAIT_CONFIGURATION:
      if(exchanged_msg[MSG_CAMP])
        imu_state = STATE_SEND_ACK;
      else
        local_strftime(updateCurrentTimestamp());
      break;
    case STATE_ACQUISITION:
      if(dataHub.connected()){
        if(!blnStop){
          uint16_t acquisitionLoopDelay = campaign_settings.interval;

          switch (campaign_settings.mode) {
            case CAMPAIGN_RAW:
              sampleAndSendBLE(true);
              break;

            case CAMPAIGN_FEATURES:
              sampleFeaturesMode();
              acquisitionLoopDelay = 1;
              break;

            case CAMPAIGN_QUAT:
              sampleComputeQuatAndSendBLE(true);
              break;

            default:
              Serial.print("Unsupported campaign mode: 0x");
              Serial.println(campaign_settings.mode, HEX);
              blnStop = true;
              break;
          }

          sampleBattery(batteryPowered);
          delay(acquisitionLoopDelay);
        } else
          imu_state = STATE_STOP;
      } else {
        unexDisconnected = true;
        imu_state = STATE_DISCONNECTION;
        disconnectStartTime = millis();
        changestate = true;
        firsttime = true;
      }
      break;
    case STATE_STOP:
      /* maybe save on the SD card in the future */
      delay(1000);
      digitalToggle(LED_RED);
      delay(1000);
      digitalToggle(LED_RED);
      if (campaign_settings.mode == CAMPAIGN_FEATURES)
        freeFeatureBuffers();

      imu_state = STATE_SLEEP;
      blnStop = false;
      changestate = true;
      break;
    /* not connected w/ anomalies */
    case STATE_DISCONNECTION:
      if(!dataHub.connected()){
        if(campaign_ongoing){ /* it should always be true if we are here */
          //if(campaign_settings.raw)
            //sampleAndSendBLE(false);
          //else
            //sampleComputeQuatAndSendBLE(false);
          //sampleBattery(false);
          //delay(campaign_settings.interval);
        //}
          // Check timeout
          Serial.println("Client disconnected: Waiting a reconnection ...");
          if(millis() - disconnectStartTime > RECONNECT_TIMEOUT_MS)
          {
            Serial.println("Timeout expired. Disconnecting. Expecting HW Reset.");
            BLE.stopAdvertise();
            BLE.disconnect();
            delay(100);
            imu_state = STATE_ZOMBIE;
            //NVIC_SystemReset();

          }
          delay(2000);
        }
      } else {
        if(campaign_ongoing){
          Serial.println("Resuming BLE communication, sending again sampled data. Going back to ACQUISIION");
          imu_state = STATE_ACQUISITION;
        } else {
          imu_state = STATE_READY;
        }
        changestate = true;
        firsttime = true;
      }
      break;    
    case STATE_ZOMBIE:
      break;
    default: /* SHOULD NOT HAPPEN REALLY */
      if(unexDisconnected) {
        if(dataHub.connected())
          decideNextStateOnReconnect();
        else
          decideNextStateOnDisconnect();
      }
  }
}

void decideNextStateOnReconnect(void){
    Serial.println("-------- Resuming BLE communication: Got lost somewhere --------");
    if(campaign_ongoing)
      imu_state = STATE_ACQUISITION;
    else
      imu_state = STATE_READY;
    changestate = true;
    firsttime = true;
    unexDisconnected = false;
}

/* needed when an unexpected disconnection occurs */
void decideNextStateOnDisconnect(void)
{
  Serial.println("xxxxxxxxxxx Interrupted BLE communication: Got lost somewhere xxxxxxxx");
  print_state();
  if(exchanged_msg[MSG_TS]) { /* at least the TS had been received */
    if(exchanged_msg[MSG_CAMP]){
      if(exchanged_msg[MSG_ACK]){
        Serial.println(" moving to STATE_READY");
        imu_state = STATE_READY;
      } else {
        Serial.println(" moving to STATE_SEND_ACK");
        imu_state = STATE_SEND_ACK;
      }
    } else {
      Serial.println(" moving to STATE_WAIT_CONFIGURATION");
      imu_state = STATE_WAIT_CONFIGURATION;
    }
  }
}

void print_state(void){
  switch(imu_state){
    case STATE_POWER_ON:
      Serial.println("POWER ON");
      break;
    case STATE_WAIT_TIMESTAMP:
      Serial.println("WAITING FOR TIMESTAMP");
      break;
    case STATE_WAIT_CONFIGURATION:
      Serial.println("WAITING FOR CONFIGURATION");
      break;
    case STATE_SEND_ACK:
      Serial.println("SENDING ACK");
      break;
    case STATE_READY:
      Serial.println("WAITING FOR START");
      break;
    case STATE_ACQUISITION:
      Serial.println("data ACQUISITION started");
      break;
    case STATE_DISCONNECTION:
      Serial.println("DISCONNECTED: lost connection to central device");
      break;
    case STATE_STOP:
      Serial.println("STOPPED by the application/user");
      break;
    case STATE_SLEEP:
      Serial.println("going into SLEEP waiting for disconnection or restart");
      break;
    case STATE_ZOMBIE:
      Serial.println("ZOMBIE");
      break;
    default:
      Serial.print("Unrecognized state");
      Serial.print(imu_state);
  }
}


bool setupSensors(void)
{
  bool res;
  if (!IMU.begin()) {
    Serial.println("Failed to initialize IMU!");
    res = false;
  } else {
    Serial.println("Sensors found");
    Serial.print("Accelerometer sample rate = ");
    Serial.print(IMU.accelerationSampleRate());
    Serial.println(" Hz");

    Serial.print("Gyroscope sample rate = ");
    Serial.print(IMU.gyroscopeSampleRate());
    Serial.println(" Hz");
  
    Serial.print("Magnetic field sample rate = ");
    Serial.print(IMU.magneticFieldSampleRate());
    Serial.println(" Hz");
    res = true;
  }
  return res;
}

void startBLEandConfigure(void) {
  BLE.setAdvertisedService(bleService);
  // add the characteristic to the service
  // receiving
  bleService.addCharacteristic(timestampCharacteristic);
  bleService.addCharacteristic(campaignCharacteristic);
  bleService.addCharacteristic(activityCharacteristic);
  // sending
  bleService.addCharacteristic(ackCharacteristic);
  // notifying
  bleService.addCharacteristic(sensorsCharacteristic);
  bleService.addCharacteristic(quatCharacteristic);
  bleService.addCharacteristic(featuresCharacteristic);

    //For reconnection
  bleService.addCharacteristic(bootIdChar);

  // add service
  BLE.addService(bleService);

  //For reconnection
  uint64_t chip_id = getDeviceID();
  boot_id = (uint32_t)(chip_id ^ micros());
  bootIdChar.writeValue(boot_id);
  Serial.print("BOOT_ID: ");
  Serial.println(boot_id);

  /* battery */
  if(batteryPowered){
    BLE.setAdvertisedService(bleBatteryService);
    bleBatteryService.addCharacteristic(batteryLevelCharacteristic);
    BLE.addService(bleBatteryService);
  }
}

void setWriteHandlers()
{
  // assign event handlers for characteristics:
  timestampCharacteristic.setEventHandler(BLEUpdated, callbackCharacteristicTimestamp);
  campaignCharacteristic.setEventHandler(BLEWritten, callbackCharacteristicConfiguration); 
  activityCharacteristic.setEventHandler(BLEWritten, callbackCharacteristicStartStop);
}

void startAdv(void) {
  BLE.advertise();
  digitalToggle(LED_BLUE);
  delay(1000);  /* two seconds to blink */
  digitalToggle(LED_BLUE);
  delay(1000);
  digitalToggle(LED_RED);
  delay(1000);  /* two seconds to blink */
  digitalToggle(LED_RED);
  delay(1000);  /* two seconds to blink */
}

/* NOT USED 
// Callback functions
void connect_callback(BLEDevice dev) {
  Serial.println("Someone connected +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++");
  Serial.println(dev.address());
  Serial.println("Someone connected +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++");
  decideNextStateOnConnect();
}


void disconnect_callback(BLEDevice dev) {
  Serial.println("Disconnected ----------------------------------------------------------------------------------------------------");
  Serial.println(dev.address());
  Serial.println("Disconnected ----------------------------------------------------------------------------------------------------");
  decideNextStateOnDisconnect();
}
*/

void sendACK_OK(){
  uint16_t payload = ACK_OK;
  ackCharacteristic.writeValue((uint8_t*)&payload, sizeof(payload));
  Serial.println("Sent ACK");
  exchanged_msg[MSG_ACK] = true;
  changestate = true;
}

void sendACK_KO(){
  uint16_t payload = ACK_KO;
  ackCharacteristic.writeValue((uint8_t*)&payload, sizeof(payload));
/*
  ackCharacteristic.notify((uint8_t*)&payload, sizeof(payload));
*/
}


//void callbackCharacteristicTimestamp(uint16_t conn_hdl, BLECharacteristic* chr, uint8_t* data, uint16_t len) {
void callbackCharacteristicTimestamp(BLEDevice dev, BLECharacteristic chr) {
  const uint8_t* data = chr.value();
  uint16_t len = chr.valueLength();
  unsigned long pTS;
	if (len == TIMESTAMP_HEX_LEN) {
  	Serial.print("Timestamp received: ");
		pTS = hex4bytes2ulong(data);
//		setTimestamp(pTS);
    initTimestamp = pTS;
    setTime(pTS);
  	Serial.print(pTS);
  	Serial.print(" > ");
//    visualiseFullDateTime();
    showDate();
    exchanged_msg[MSG_TS] = true;
	} else {
		Serial.println("Timestamp: Invalid payload length");
		Serial.println(len);
	}
}

//void callbackCharacteristicConfiguration(uint16_t conn_hdl, BLECharacteristic* chr, uint8_t* data, uint16_t len) {
void callbackCharacteristicConfiguration(BLEDevice dev, BLECharacteristic chr) {
  Serial.println("Configuration received");

  const uint8_t* data = chr.value();
  uint16_t len = chr.valueLength();

  /*
   * 6-byte campaign configuration, little-endian:
   * byte 0     sampling_frequency
   * byte 1     mode
   * byte 2-3   window_size
   * byte 4-5   step_size
   *
   * Counter is no longer configured by the client: every campaign starts at 0.
   */
  if (len == CONFIGURATION_HEX_LEN) {
    campaign_settings.sampling_frequency = data[0];
    campaign_settings.mode = data[1];
    campaign_settings.window_size =
        ((uint16_t)data[3] << 8) | (uint16_t)data[2];
    campaign_settings.step_size =
        ((uint16_t)data[5] << 8) | (uint16_t)data[4];

    bool frequencyValid =
        campaign_settings.sampling_frequency > 0 &&
        campaign_settings.sampling_frequency <= MAX_IMU_SAMPLING_FREQUENCY;

    bool modeValid =
        campaign_settings.mode == CAMPAIGN_RAW ||
        campaign_settings.mode == CAMPAIGN_FEATURES ||
        campaign_settings.mode == CAMPAIGN_QUAT;

    bool preprocessingParametersValid = true;
    if (campaign_settings.mode == CAMPAIGN_FEATURES) {
      preprocessingParametersValid =
          campaign_settings.window_size > 0 &&
          campaign_settings.step_size > 0 &&
          campaign_settings.step_size <= campaign_settings.window_size;
    }

    if (!frequencyValid || !modeValid || !preprocessingParametersValid) {
      Serial.println("Configuration rejected.");

      if (!frequencyValid) {
        Serial.print("Invalid sampling frequency for BMI270: ");
        Serial.println(campaign_settings.sampling_frequency);
        Serial.print("Maximum supported by current sensor configuration: ");
        Serial.println(MAX_IMU_SAMPLING_FREQUENCY);
      }

      if (!modeValid) {
        Serial.print("Invalid mode: 0x");
        Serial.println(campaign_settings.mode, HEX);
      }

      if (!preprocessingParametersValid) {
        Serial.print("Invalid window/step: ");
        Serial.print(campaign_settings.window_size);
        Serial.print(" / ");
        Serial.println(campaign_settings.step_size);
      }

      exchanged_msg[MSG_CAMP] = false;
      return;
    }

    campaign_settings.interval =
        (SAMPL_FREQ_ADJ * 1000) /
        campaign_settings.sampling_frequency;

    counter = 0;

    if (campaign_settings.mode == CAMPAIGN_FEATURES) {
      if (!allocateFeatureBuffers(campaign_settings.window_size)) {
        Serial.println("Configuration rejected: FEATURES RAM allocation failed.");
        exchanged_msg[MSG_CAMP] = false;
        return;
      }
    } else {
      freeFeatureBuffers();
    }

    Serial.println("Campaign configuration:");
    Serial.print(" counter initial value: ");
    Serial.println(counter);
    Serial.print(" sampling frequency (Hz): ");
    Serial.println(campaign_settings.sampling_frequency);
    Serial.print(" sampling interval RAW (ms): ");
    Serial.println(campaign_settings.interval);
    Serial.print(" mode: 0x");
    Serial.println(campaign_settings.mode, HEX);
    Serial.print(" window size (samples): ");
    Serial.println(campaign_settings.window_size);
    Serial.print(" step size (samples): ");
    Serial.println(campaign_settings.step_size);

    exchanged_msg[MSG_CAMP] = true;
    imu_state = STATE_SEND_ACK;
  } else {
    Serial.print("Configuration: Invalid payload length: ");
    Serial.println(len);
    Serial.print("Expected: ");
    Serial.println(CONFIGURATION_HEX_LEN);
  }
}

//void callbackCharacteristicStartStop(uint16_t conn_hdl, BLECharacteristic* chr, uint8_t* data, uint16_t len) {
void callbackCharacteristicStartStop(BLEDevice dev, BLECharacteristic chr) {
  // Get data and length
  const uint8_t* data = chr.value();
  uint16_t len = chr.valueLength();
  uint8_t i;

	if (len == 1) {
    Serial.println("Start/Stop received");
		if(data[0] == START_CAMPAIGN){
			Serial.println("STARTING");
      campaign_ongoing = true;
      blnStart = true;
		} else if (data[0] == STOP_CAMPAIGN){
			Serial.println("STOPPING");
      blnStop = true;
      /* campaign reset */
      campaign_ongoing = false;
      for(i = 0; i < REQ_MSG; i++)
        exchanged_msg[i] = false;
			Serial.println(" moving to STATE_STOP");
		}
	} else {
    Serial.println(len);
    for(; len >=0; len--)
      Serial.println(data[len]);
		Serial.println("Start/Stop: Invalid payload length");
	}
}

/* utilities */

unsigned long hex4bytes2ulong(const uint8_t* data){
  return ((unsigned long)data[0] << 24) |
          ((unsigned long)data[1] << 16) |
          ((unsigned long)data[2] << 8)  |
          ((unsigned long)data[3]);
}


/* IMU SPECIFIC */

void sampleAndSendBLE(bool blnSend)
{
  time_t nowts;
  uint16_t cents;
  datapacket_t payload;
  uint8_t blepayload[28];

  int16_t ax, ay, az;
  int16_t gx, gy, gz;
  int16_t mx, my, mz;

  // BMI270 optimization: ACC+GYRO are read together with one sensor API call.
  IMU.readAccelGyroRaw(ax, ay, az, gx, gy, gz);
  IMU.readMagneticFieldRaw(mx, my, mz);

  payload.ax = ax;
  payload.ay = ay;
  payload.az = az;
  payload.gx = gx;
  payload.gy = gy;
  payload.gz = gz;
  payload.mx = mx;
  payload.my = my;
  payload.mz = mz;
	payload.counter = counter;
  payload.timestamp = updateCurrentTimestamp();
  //
  if(blnSend){
    memcpy(blepayload, &payload, payload_size);
    sensorsCharacteristic.writeValue((uint8_t*)&blepayload, sizeof(blepayload), false);
    printPayloadHEX(blepayload, sizeof(blepayload));
  }
  counter++;
}

void sampleBattery(bool blnSend){
  unsigned long currentTime = millis();
  int voltage;
  if(currentTime - lastSampleTime >= BATTERY_SAMPLING_FREQUENCY){
    lastSampleTime = currentTime;
    voltage = readBatteryVoltageRaw();
    Serial.print("battery voltage ");
    Serial.println(voltage);
    batteryLevelCharacteristic.writeValue((uint8_t*)&voltage, sizeof(float), false);
  }
}


void printPayloadHEX(uint8_t payload[], int dim)
{
  for(int i = 0; i < dim; i++)
  {
    Serial.print(payload[i]);
    Serial.print(" ");
  }
  Serial.print(" ");
  showDate();
//  Serial.println(" ");
}

void printPayload(datapacket_t payload)
{
  Serial.print(payload.ax);
  Serial.print(" ");
  Serial.print(payload.ay);
  Serial.print(" ");
  Serial.print(payload.az);
  Serial.print(" ");
  Serial.print(payload.gx);
  Serial.print(" ");
  Serial.print(payload.gy);
  Serial.print(" ");
  Serial.print(payload.gz);
  Serial.print(" ");
  Serial.print(payload.mx);
  Serial.print(" ");
  Serial.print(payload.my);
  Serial.print(" ");
  Serial.print(payload.mz);
  Serial.println(" ");
}

void sampleComputeQuatAndSendBLE(bool blnSend)
{
  datapacket_quat_t payload;
  time_t nowts;
  uint8_t blepayload[28];
  //acc = IMU.calcAccel();
  //gyr = IMU.calcGyr();

  payload.q0 = 0;
  payload.q1 = 1;
  payload.q2 = 2;
  payload.q3 = 3;
  payload.timestamp = updateCurrentTimestamp();
	payload.counter = counter;
  
  if(blnSend){
    memcpy(blepayload, &payload, payload_size);
    quatCharacteristic.writeValue((uint8_t*)&blepayload, sizeof(blepayload));
    /*
    quatCharacteristic.notify((uint8_t*)&payload, sizeof(payload));
    */
  }
  /* next sample */
  counter++;
}

float readBatteryVoltage() {
  int raw = analogRead(BATTERY_PIN);
  float voltage = ((float)raw / ADC_RESOLUTION) * ADC_REF_VOLTAGE * VOLTAGE_DIVIDER_RATIO;
  return voltage;
}

float readBatteryVoltageRaw() {
  int raw = analogRead(BATTERY_PIN);
  return raw;
}


/* keep the time */
void setTimestamp(time_t ts) {
  initTimestamp = ts;
  baseMillis = millis();  /* how long since wakeup */
}

time_t updateCurrentTimestamp(void) {
  unsigned long elapsedMillis = millis() - baseMillis;
  unsigned long nowts = initTimestamp + (elapsedMillis / 1000);
//  Serial.print("ts ");
//  Serial.println(nowts);
  return nowts;
}

void currentTimestampCent(time_t * ts, uint16_t * centsec) {
  time_t elapsedMillis = millis() - baseMillis;
  *centsec = (elapsedMillis % 1000);
  *ts = initTimestamp + (elapsedMillis / 1000);
}

void local_strftime(time_t nowts){
	uint8_t daysOfMonth[] = { 31, 28, 31, 30, 31, 30,
														31, 31, 30, 31, 30, 31 };

	time_t        extraTime;
	uint16_t 			daysTillNow, numDaysInYear, extraDays, currYear, date, month, hours, minutes, seconds;
	uint8_t     	isleap;
	long 					diff;

	// Calculate total days unix time T
	daysTillNow = nowts / (24 * 60 * 60); /* number of seconds in a normal day */
	currYear = 1970;
 
	// Calculating current year
	while (true) {
		isleap = (currYear % 400 == 0 || (currYear % 4 == 0 && currYear % 100 != 0));
		numDaysInYear = 365 + isleap;
		if (daysTillNow < numDaysInYear)
				break;
		daysTillNow -= numDaysInYear;
		currYear += 1;
	}

  ts.yy = currYear - 2000;// currYear - 2000;
	extraDays = daysTillNow + 1;

  isleap = (currYear % 400 == 0 || (currYear % 4 == 0 && currYear % 100 != 0));
 
  ts.mm = 0;
  daysTillNow = 0;
	diff = extraDays - daysTillNow - daysOfMonth[ts.mm];
	while(ts.mm < 12 && diff > 0){
		daysTillNow += (daysOfMonth[ts.mm] + isleap * (ts.mm == 2));
		ts.mm += 1; 
		diff = extraDays - daysTillNow - daysOfMonth[ts.mm];
	}
	ts.mm += 1; 
	if(extraDays - daysTillNow > 0){
		ts.dd = extraDays - daysTillNow;
	} else {
		ts.dd = daysOfMonth[ts.mm] + isleap * (ts.mm == 2);
	}

  extraTime = nowts % (24 * 60 * 60);
  /* remaining time */
  ts.HH = extraTime / 3600;
  extraTime = (extraTime % 3600);
  ts.MM = (extraTime % 3600) / 60;
  ts.SS = (extraTime % 3600) % 60;
  ts.cents = 0;
}

void showDate()
{
  Serial.print(" ");
  Serial.print(year());
  Serial.print('-');
  if(month() <= 9)
    Serial.print("0");
  Serial.print(month());
  Serial.print('-');
  if(day() <= 9)
    Serial.print("0");
  Serial.print(day());
  Serial.print("T");
  if(hour() <= 9)
    Serial.print("0");
  Serial.print(hour());
  Serial.print(':');
  if(minute() <= 9)
    Serial.print("0");
  Serial.print(minute());
  Serial.print(':');
  if(second() <= 9)
    Serial.print("0");
  Serial.println(second());  
}

void visualiseFullDateTime(void)
{
  /* log */
  Serial.print("20");
  if(ts.yy < 10)
    Serial.print("0");
  Serial.print(ts.yy);
  Serial.print("-");
  if(ts.mm <= 9)
    Serial.print("0");
  Serial.print(ts.mm);
  Serial.print("-");
  if(ts.dd <= 9)
    Serial.print("0");
  Serial.print(ts.dd);
  Serial.print("T");
  if(ts.HH+2 <= 9)
    Serial.print("0");
  Serial.print(ts.HH+2);
  Serial.print(":");
  if(ts.MM <= 9)
    Serial.print("0");
  Serial.print(ts.MM);
  Serial.print(":");
  if(ts.SS <= 9)
    Serial.print("0");
  Serial.print(ts.SS);
  Serial.print(".");
  Serial.println(ts.cents);
}

void byte_to_str(char s[], uint16_t b)
{
  uint8_t val;

  val = b & 0x0F;
  if(val < 10)
    s[1] = '0' + val;
  else
    s[1] = 'A' + (val - 10);
  val = b >> 4;
  if(val < 10)
    s[0] = '0' + val;
  else
    s[10] = 'A' + (val - 10);
}

void digitalToggle(uint8_t led)
{
  if(digitalRead(led) == HIGH)
    digitalWrite(led, LOW);
  else
    digitalWrite(led, HIGH);
}


/* battery */
PowerSource detectPowerSource() {
  float usbVoltage = readUSBVoltage();
  
  // If USB voltage is above threshold, USB is connected
  if (usbVoltage > USB_THRESHOLD) {
    return POWER_USB;
  } else {
    return POWER_BATTERY;
  }
}


float readUSBVoltage() {
  // Read from A6 which has voltage divider for USB detection
  int analogValue = analogRead(USB_VOLTAGE_PIN);
  
  // Convert to voltage
  // A6 has a voltage divider (typically 1/2 ratio)
  // So multiply by 2 to get actual USB voltage
  float voltage = (analogValue * 3.3 / 1024.0) * 2.0;
  
  return voltage;
}

float readVCCVoltage() {
  // Read internal VCC voltage
  // This gives us the actual supply voltage to the MCU
  
  // Use internal reference to measure VCC
  analogReference(AR_INTERNAL1V2);
  delay(10);  // Allow reference to settle
  
  int analogValue = analogRead(BATTERY_PIN);  // BATTERY_PIN is connected to VCC/4
  
  // Calculate VCC voltage
  float vcc = (1.2 * 1024 / analogValue) * 4;
  
  // Restore normal reference
  analogReference(AR_VDD);
  
  return vcc;
}