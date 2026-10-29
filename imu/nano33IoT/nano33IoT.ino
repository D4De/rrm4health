
/* Select board Nano 33 IoT sense nRF52840 */

#include <Arduino_LSM6DS3.h>
#include <ArduinoBLE.h>
#include <TimeLib.h>
#include <SPI.h>
#include <WiFiNINA.h>
#include <WiFiUdp.h>
#include <ArduinoMDNS.h>

//For reconnection
#define RECONNECT_TIMEOUT_MS 30000  // 30 seconds

#define IMU_DEFAULT_NAME  "IMUXXXX"
typedef volatile uint32_t REG32;
#define pREG32 (REG32 *)
#define MAC_ADDRESS_HIGH  (*(pREG32 (0x100000a8)))
#define MAC_ADDRESS_LOW   (*(pREG32 (0x100000a4)))

/* Nano 33 BLE sense */
/* Analog pin used to read battery voltage (through voltage divider) */
#define BATTERY_PIN                           A0
#define USB_VOLTAGE_PIN                       A6
#define USB_THRESHOLD                         4.5f
#define BATTERY_PRESENT_THRESHOLD              2.5f
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
#define BATTLEVEL_HEX_LEN                     1 /* standard Battery Level: 0-100% */

#define START_CAMPAIGN                        0x00
#define STOP_CAMPAIGN                         0x0F
#define CAMPAIGN_RAW                          0x00
#define CAMPAIGN_FEATURES                     0x01
#define CAMPAIGN_QUAT                         0x0F

#define DEFAULT_COUNTER_INIT                  0
#define DEFAULT_SAMPLING_FREQUENCY            10 /* 10 Hz - 10 samples in a second */
#define MAX_IMU_SAMPLING_FREQUENCY            104
#define DEFAULT_TIMESTAMP_INIT                0

#define SAMPL_FREQ_ADJ                        0.5  /* the sampling is not precise ... */
#define BATTERY_SAMPLING_FREQUENCY            10000 /* 30 seconds */

#define MSG_TS                                0
#define MSG_CAMP                              1
#define MSG_ACK                               1
#define REQ_MSG                               3 /* timestamp, initial counter, ack */

/* typedefs */

typedef struct {
  float x, y, z;
} sensor_data_t;

typedef struct _datapacket {  /* 3 x 2 x 3 bytes + 2 bytes + 2 bytes + 4 bytes = 26 */
  uint16_t ax, ay, az;  /* raw values */
  uint16_t gx, gy, gz;
  uint16_t mx, my, mz;
  uint16_t counter;
  uint32_t timestamp;
} datapacket_t;

typedef struct _datapacket_quat {  /* 4 x 4 bytes + 2 bytes + 4 bytes = 22 */
  uint32_t q0, q1, q2, q3;  /* aggregated values */
  uint16_t counter;
  uint32_t timestamp;
} datapacket_quat_t;

#define FEATURE_COUNT 28
typedef struct __attribute__((packed)) _featurepacket {
  float features[FEATURE_COUNT];
  uint16_t counter;
  uint32_t timestamp;
} featurepacket_t;
static_assert(sizeof(featurepacket_t) == 118, "Unexpected featurepacket_t size");

typedef struct _campaignpar {
  uint8_t   sampling_frequency;
  uint16_t  interval;
  uint8_t   mode;
  uint16_t  window_size;
  uint16_t  step_size;
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
///////////////////////////////////////////////////////////////

///////////////////////For IoT Wifi
#define LED_BLUE LED_BUILTIN
#define LED_RED  LED_BUILTIN

typedef enum {
  MODE_NONE = 0,
  MODE_WIFI,
  MODE_BLE
} comm_mode_t;

comm_mode_t comm_mode = MODE_NONE;

///////////////////////////////////

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

//For reconnection
unsigned long disconnectStartTime = 0;
uint32_t boot_id;

uint64_t getDeviceID() {
  return random(0xFFFFFFFF);
}
////////////

//For WIFI ///////////////////////////
#include <SPI.h>
#include <WiFiNINA.h>
#include <WiFiUdp.h>
#include <ArduinoMDNS.h>

//#define STASSID "WIFI_126"
//#define STAPSK  "126_WIFI"

#define STASSID "XXXXX"
#define STAPSK  "XXXXX"
/* =======================
   WiFi credentials
   ======================= */
char ssid[] = STASSID;
char pass[] = STAPSK;
int status = WL_IDLE_STATUS;

/* =======================
   TCP config
   ======================= */
constexpr uint16_t TCP_PORT = 8023;

/* =======================
   Oggetti WiFi
   ======================= */
WiFiServer server(TCP_PORT);
WiFiClient client;
WiFiUDP udp;
MDNS mdns(udp);
/* =======================
   Logging
   ======================= */
#define LOG_INFO(x)   { Serial.print("[INFO] ");  Serial.println(x);}
#define LOG_WARN(x)   { Serial.print("[WARN] ");  Serial.println(x); }
#define LOG_ERROR(x)  { Serial.print("[ERROR] "); Serial.println(x); }
////////////////////////////////////////////////////////////////////////////


uint8_t                                       payload_size = sizeof(datapacket_t);

volatile bool                                 exchanged_msg[REQ_MSG]; 
volatile bool                                 blnStart;
volatile bool                                 blnStop;
volatile bool                                 campaign_ongoing;
bool                                          batteryPowered;



#define FEATURE_FILTER_ENABLED 1
const float FEATURE_B0=0.04613188f, FEATURE_B1=0.09226376f, FEATURE_B2=0.04613188f;
const float FEATURE_A1=-1.30728503f, FEATURE_A2=0.49181255f;

class FeatureBiquadFilter {
  float x1=0,x2=0,y1=0,y2=0;
 public:
  void reset(){x1=x2=y1=y2=0;}
  float process(float x){
    float y=FEATURE_B0*x+FEATURE_B1*x1+FEATURE_B2*x2-FEATURE_A1*y1-FEATURE_A2*y2;
    x2=x1; x1=x; y2=y1; y1=y; return y;
  }
};

FeatureBiquadFilter featureFilterAx,featureFilterAy,featureFilterAz;
FeatureBiquadFilter featureFilterGx,featureFilterGy,featureFilterGz;
float *featureAxBuffer=NULL,*featureAyBuffer=NULL,*featureAzBuffer=NULL;
float *featureGxBuffer=NULL,*featureGyBuffer=NULL,*featureGzBuffer=NULL;
uint16_t featureSampleCount=0;
uint32_t featureLastSampleUs=0;
bool featureBuffersReady=false;

void resetFeatureFilters(){
  featureFilterAx.reset(); featureFilterAy.reset(); featureFilterAz.reset();
  featureFilterGx.reset(); featureFilterGy.reset(); featureFilterGz.reset();
}

void freeFeatureBuffers(){
  if(featureAxBuffer)free(featureAxBuffer); if(featureAyBuffer)free(featureAyBuffer);
  if(featureAzBuffer)free(featureAzBuffer); if(featureGxBuffer)free(featureGxBuffer);
  if(featureGyBuffer)free(featureGyBuffer); if(featureGzBuffer)free(featureGzBuffer);
  featureAxBuffer=featureAyBuffer=featureAzBuffer=NULL;
  featureGxBuffer=featureGyBuffer=featureGzBuffer=NULL;
  featureSampleCount=0; featureLastSampleUs=0; featureBuffersReady=false;
}

bool allocateFeatureBuffers(uint16_t w){
  freeFeatureBuffers();
  size_t bytes=(size_t)w*sizeof(float);
  featureAxBuffer=(float*)malloc(bytes); featureAyBuffer=(float*)malloc(bytes);
  featureAzBuffer=(float*)malloc(bytes); featureGxBuffer=(float*)malloc(bytes);
  featureGyBuffer=(float*)malloc(bytes); featureGzBuffer=(float*)malloc(bytes);
  if(!featureAxBuffer||!featureAyBuffer||!featureAzBuffer||!featureGxBuffer||!featureGyBuffer||!featureGzBuffer){
    freeFeatureBuffers(); return false;
  }
  memset(featureAxBuffer,0,bytes); memset(featureAyBuffer,0,bytes); memset(featureAzBuffer,0,bytes);
  memset(featureGxBuffer,0,bytes); memset(featureGyBuffer,0,bytes); memset(featureGzBuffer,0,bytes);
  featureBuffersReady=true; resetFeatureFilters(); return true;
}

void shiftFeatureWindow(){
  uint16_t w=campaign_settings.window_size,s=campaign_settings.step_size;
  if(s>=w){featureSampleCount=0;return;}
  uint16_t r=w-s; size_t rb=(size_t)r*sizeof(float), sb=(size_t)s*sizeof(float);
  memmove(featureAxBuffer,(uint8_t*)featureAxBuffer+sb,rb);
  memmove(featureAyBuffer,(uint8_t*)featureAyBuffer+sb,rb);
  memmove(featureAzBuffer,(uint8_t*)featureAzBuffer+sb,rb);
  memmove(featureGxBuffer,(uint8_t*)featureGxBuffer+sb,rb);
  memmove(featureGyBuffer,(uint8_t*)featureGyBuffer+sb,rb);
  memmove(featureGzBuffer,(uint8_t*)featureGzBuffer+sb,rb);
  featureSampleCount=r;
}

/*
 * TO ADD/REMOVE FEATURES:
 * 1) change FEATURE_COUNT;
 * 2) modify extractFeatureVector() and outFeatures[index];
 * 3) update FEATURE_NAMES in the Python manager in the same order;
 * 4) if new sensors are needed, extend buffers/sampling too.
 */
void extractFeatureVector(float* o){
  uint16_t n=campaign_settings.window_size;
  double sa=0,sb=0,sc=0,sgx=0,sgy=0,sgz=0,sam=0,sgm=0;
  float maxa=0,maxg=0,maxax=featureAxBuffer[0],maxay=featureAyBuffer[0],maxaz=featureAzBuffer[0];
  float maxgx=featureGxBuffer[0],maxgy=featureGyBuffer[0],maxgz=featureGzBuffer[0];
  for(uint16_t i=0;i<n;i++){
    float ax=featureAxBuffer[i],ay=featureAyBuffer[i],az=featureAzBuffer[i];
    float gx=featureGxBuffer[i],gy=featureGyBuffer[i],gz=featureGzBuffer[i];
    sa+=ax;sb+=ay;sc+=az;sgx+=gx;sgy+=gy;sgz+=gz;
    if(ax>maxax)maxax=ax;if(ay>maxay)maxay=ay;if(az>maxaz)maxaz=az;
    if(gx>maxgx)maxgx=gx;if(gy>maxgy)maxgy=gy;if(gz>maxgz)maxgz=gz;
    float am=sqrtf(ax*ax+ay*ay+az*az),gm=sqrtf(gx*gx+gy*gy+gz*gz);
    sam+=am;sgm+=gm;if(am>maxa)maxa=am;if(gm>maxg)maxg=gm;
  }
  float maxn=n;
  float ma=sa/maxn,mb=sb/maxn,mc=sc/maxn,mgx=sgx/maxn,mgy=sgy/maxn,mgz=sgz/maxn;
  float mam=sam/maxn,mgm=sgm/maxn;
  double va=0,vb=0,vc=0,vgx=0,vgy=0,vgz=0,vam=0,vgm=0,sma=0,js=0; float jm=0,prev=0;
  for(uint16_t i=0;i<n;i++){
    float ax=featureAxBuffer[i],ay=featureAyBuffer[i],az=featureAzBuffer[i];
    float gx=featureGxBuffer[i],gy=featureGyBuffer[i],gz=featureGzBuffer[i];
    float am=sqrtf(ax*ax+ay*ay+az*az),gm=sqrtf(gx*gx+gy*gy+gz*gz);
    float da=ax-ma,db=ay-mb,dc=az-mc,dgx=gx-mgx,dgy=gy-mgy,dgz=gz-mgz,dam=am-mam,dgm=gm-mgm;
    va+=da*da;vb+=db*db;vc+=dc*dc;vgx+=dgx*dgx;vgy+=dgy*dgy;vgz+=dgz*dgz;vam+=dam*dam;vgm+=dgm*dgm;
    sma+=fabsf(da)+fabsf(db)+fabsf(dc);
    if(i>0){float j=fabsf(am-prev);js+=j;if(j>jm)jm=j;} prev=am;
  }
  o[0]=maxa;o[1]=mam;o[2]=sqrtf(vam/n);o[3]=maxg;o[4]=mgm;o[5]=sqrtf(vgm/n);
  o[6]=ma;o[7]=maxax;o[8]=sqrtf(va/n);o[9]=mb;o[10]=maxay;o[11]=sqrtf(vb/n);
  o[12]=mc;o[13]=maxaz;o[14]=sqrtf(vc/n);o[15]=mgx;o[16]=maxgx;o[17]=sqrtf(vgx/n);
  o[18]=mgy;o[19]=maxgy;o[20]=sqrtf(vgy/n);o[21]=mgz;o[22]=maxgz;o[23]=sqrtf(vgz/n);
  float tr=constrain(ma/(mam+0.000001f),-1.0f,1.0f);
  o[24]=acosf(tr)*(180.0f/PI);o[25]=sma/n;o[26]=jm;o[27]=(n>1)?js/(n-1):0;
}

bool sendFeatureVector(){
  featurepacket_t p; extractFeatureVector(p.features); p.counter=counter; p.timestamp=updateCurrentTimestamp();
  bool ok=false;
  if(comm_mode==MODE_WIFI){
    size_t w=client.write((uint8_t*)&p,sizeof(p)); ok=(w==sizeof(p));
  } else if(comm_mode==MODE_BLE){
    ok=featuresCharacteristic.writeValue((uint8_t*)&p,sizeof(p),false);
  }
  counter++; return ok;
}

void sampleFeaturesMode(){
  if(!featureBuffersReady)return;
  uint32_t now=micros(), period=1000000UL/campaign_settings.sampling_frequency;
  if(featureLastSampleUs && (uint32_t)(now-featureLastSampleUs)<period)return;
  if(!featureLastSampleUs)featureLastSampleUs=now; else featureLastSampleUs+=period;
  if((uint32_t)(now-featureLastSampleUs)>2UL*period)featureLastSampleUs=now;

  float ax,ay,az,gx,gy,gz;
  if(!IMU.readAccelGyro(ax,ay,az,gx,gy,gz))return;
#if FEATURE_FILTER_ENABLED
  ax=featureFilterAx.process(ax);ay=featureFilterAy.process(ay);az=featureFilterAz.process(az);
  gx=featureFilterGx.process(gx);gy=featureFilterGy.process(gy);gz=featureFilterGz.process(gz);
#endif
  uint16_t i=featureSampleCount;
  featureAxBuffer[i]=ax;featureAyBuffer[i]=ay;featureAzBuffer[i]=az;
  featureGxBuffer[i]=gx;featureGyBuffer[i]=gy;featureGzBuffer[i]=gz;
  featureSampleCount++;
  if(featureSampleCount>=campaign_settings.window_size){sendFeatureVector();shiftFeatureWindow();}
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
  //analogReference(AR_VDD);

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

  // Keep BLE callbacks aligned with the BLE-only firmware.
  BLE.setEventHandler(BLEConnected, connect_callback);
  BLE.setEventHandler(BLEDisconnected, disconnect_callback);

  /* check if battery powered */
  Serial.print("Detected battery voltage: ");
  Serial.println(readBatteryVoltage(), 3);

  PowerSource source = detectPowerSource();
  if (source == POWER_BATTERY) {
    Serial.println("Battery powered");
    batteryPowered = true;
  } else if (source == POWER_USB) {
    Serial.println("USB powered");
    batteryPowered = false;
  } else {
    Serial.println("No battery detected");
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

  //Checking WIFI //////////////////////////////////////

  if (WiFi.status() == WL_NO_MODULE) {
    LOG_ERROR("Communication with WiFi module failed!");
    while (true);
  }

  String fv = WiFi.firmwareVersion();
  if (fv < WIFI_FIRMWARE_LATEST_VERSION) {
    LOG_WARN("Please upgrade the firmware");
  }

  /* Avvio server TCP */
  server.begin();
  LOG_INFO(String("TCP server started on port ") + TCP_PORT);
  ////////////////////////////////////////////////////////

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
  BLE.poll();
  BLEDevice dataHub = BLE.central();
  static uint16_t step = 0;

  if (comm_mode == MODE_NONE || comm_mode == MODE_WIFI) {

    status = WiFi.status();

    if (status != WL_CONNECTED) {
      Serial.print("Attempting to connect to WPA SSID: ");
      Serial.println(ssid);
      status = WiFi.begin(ssid, pass);
      if (status == WL_CONNECTED)
        LOG_INFO("WiFi connected");
      //delay(1000);
    }

    if (status == WL_CONNECTED && comm_mode != MODE_WIFI) {
      LOG_INFO("WiFi connected switching mode WIFI");
      comm_mode = MODE_WIFI;
      //BLE.stopAdvertise();
      //BLE.disconnect();
      // Initialize the mDNS library. You can now reach or ping this
      // Arduino via the host name "arduino.local", provided that your operating
      // system is mDNS/Bonjour-enabled (such as macOS).
      // Always call this before any other method!
      mdns.begin(WiFi.localIP(), "imu-01");
      printCurrentNet();
      printWifiData();
    }
  }

  if (comm_mode == MODE_NONE && dataHub) {
    Serial.println("BLE central connected. Switching to BLE mode.");
    comm_mode = MODE_BLE;
  }
  ////////////////////////////////////////////////////////

  if(firsttime){
    print_state();
    firsttime = false;
  }
  if(imu_state == STATE_POWER_ON)
    everConnected = false;
  step++;

  bool isConnected = false;

  if(comm_mode == MODE_BLE)
  {
    isConnected = dataHub.connected();
  }
  else if(comm_mode == MODE_WIFI)
  {
    if (!client || !client.connected()) {
      client = server.available();
    }

    isConnected = client && client.connected();

    if (client && client.available()) {
      //BLE.stopAdvertise();
      //BLE.disconnect();
      handleWiFi(client);
    }
  }

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
      }
      break;
    case STATE_SLEEP: /* waiting for disconnection or new campaign */
      if(!isConnected){
        Serial.println(" Campaign concluded. Moving to POWER_ON for another campaign");
        imu_state = STATE_POWER_ON;
        everConnected = false;
        changestate = true;  
        resetCommunication();
        comm_mode = MODE_NONE;
      } else {
        delay(1000);
      }
      break;
    case STATE_SEND_ACK:
      if(isConnected){
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
      if(isConnected){
        if(!blnStop){
          uint16_t acquisitionLoopDelay=campaign_settings.interval;
          switch(campaign_settings.mode){
            case CAMPAIGN_RAW: sampleAndSendBLE(true); break;
            case CAMPAIGN_FEATURES: sampleFeaturesMode(); acquisitionLoopDelay=1; break;
            case CAMPAIGN_QUAT: sampleComputeQuatAndSendBLE(true); break;
            default: blnStop=true; break;
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
      if(campaign_settings.mode==CAMPAIGN_FEATURES) freeFeatureBuffers();
      imu_state = STATE_SLEEP;
      blnStop = false;
      changestate = true;
      break;
    /* not connected w/ anomalies */
    case STATE_DISCONNECTION:
      if(!isConnected){
        if(campaign_ongoing){ /* it should always be true if we are here */
          //if(campaign_settings.raw)
            //sampleAndSendBLE(false);
          //else
            //sampleComputeQuatAndSendBLE(false);
          //sampleBattery(false);

          // Check timeout
          Serial.println("Client disconnected: Waiting a reconnection ...");
          if(millis() - disconnectStartTime > RECONNECT_TIMEOUT_MS)
          {
            Serial.println("Reconnect timeout expired. Communication session aborted.");
            resetCommunication();
            imu_state = STATE_ZOMBIE;

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
        if(isConnected)
          decideNextStateOnReconnect();
        else
          decideNextStateOnDisconnect();
      }
  }
}
// Reset communication ////////
void resetCommunication()
{
  // --- Reset WiFi ---
  if (comm_mode == MODE_WIFI) {

    if (client && client.connected()) 
    {
      client.stop();
    }

    status = WiFi.disconnect();   // true = erase old connection
    //startAdv();
  }

  // --- Reset BLE ---
  if (comm_mode == MODE_BLE) {

    if (BLE.connected()) {
      BLE.disconnect();
    }
  }

  comm_mode = MODE_NONE;
}

// Handler WIFI //////////////////////////////////////////////////
void handleWiFi(WiFiClient client)
{
  if (!client) return;

  if (client.available()) 
  {

    //uint8_t buffer[32];
    //int len = client.read(buffer, sizeof(buffer));

    //uint8_t msgType = buffer[0];
    //uint8_t* payload = &buffer[1];
    //uint16_t payloadLen = len - 1;

    String request = client.readStringUntil('\n');
    request.trim();

    LOG_INFO(String("RX: ") + request);

    if (request.equalsIgnoreCase("PING")) {
      client.println("PONG");
    }
    else if (request.equalsIgnoreCase("HELLO")) {
      client.println("HELLO FROM NANO 33 IOT");
    }
    else if (request.equalsIgnoreCase("BYE")) {
      client.println("GOODBYE");
      client.stop();
      LOG_INFO("Client disconnected by command");
    }
    else if (request.startsWith("CONFIG:")) {
      handleConfigurationMessage(request);
    }
    else if (request.startsWith("TIMESTAMP:")) {
      handleTimestampMessage(request);
    }
    else if (request.startsWith("ACTIVITY:")) {
      handleActivityMessage(request);
    }
    else if (request.equalsIgnoreCase("BOOT_ID")) {
      client.println(boot_id);
    }
    else if (request.equalsIgnoreCase("BATTERY")) {
      if (batteryPowered) {
        uint8_t batteryLevel = refreshBatteryLevel();
        client.print("BATTERY:");
        client.println(batteryLevel);
      } else {
        client.println("BATTERY:NA");
      }
    }
    else {
      client.println("UNKNOWN COMMAND");
      LOG_WARN("Unknown command");
    }
  }
}

void handleTimestampMessage(String request)
{
  String payload = request.substring(10);
  Serial.print("Timestamp received: ");
  unsigned long pTS = payload.toInt();
  initTimestamp = pTS;
  setTime(pTS);
  setTimestamp(pTS);
  Serial.print(pTS);
  Serial.print(" > ");
  showDate();
  exchanged_msg[MSG_TS] = true;

}

void handleConfigurationMessage(String request)
{
  String payload=request.substring(7);
  int sampling_frequency=0,window_size=300,step_size=100;
  bool raw=true;

  int pos=0;
  while(pos<payload.length()){
    int sep=payload.indexOf(',',pos);
    String token=(sep==-1)?payload.substring(pos):payload.substring(pos,sep);
    int eq=token.indexOf('=');
    if(eq>0){
      String key=token.substring(0,eq),value=token.substring(eq+1);
      key.trim();value.trim();
      if(key=="sampling_frequency")sampling_frequency=value.toInt();
      else if(key=="raw")raw=value.equalsIgnoreCase("true");
      else if(key=="window_size")window_size=value.toInt();
      else if(key=="step_size")step_size=value.toInt();
    }
    if(sep==-1)break;
    pos=sep+1;
  }

  if(sampling_frequency<=0||sampling_frequency>MAX_IMU_SAMPLING_FREQUENCY){
    client.println("ERR:CONFIG");return;
  }

  campaign_settings.sampling_frequency=(uint8_t)sampling_frequency;
  campaign_settings.mode=raw?CAMPAIGN_RAW:CAMPAIGN_FEATURES;
  campaign_settings.window_size=(uint16_t)window_size;
  campaign_settings.step_size=(uint16_t)step_size;
  campaign_settings.interval=(SAMPL_FREQ_ADJ*1000)/campaign_settings.sampling_frequency;

  if(campaign_settings.mode==CAMPAIGN_FEATURES){
    if(window_size<=0||step_size<=0||step_size>window_size||
       !allocateFeatureBuffers(campaign_settings.window_size)){
      client.println("ERR:CONFIG");return;
    }
  }else freeFeatureBuffers();

  counter=0;
  exchanged_msg[MSG_CAMP]=true;
  imu_state=STATE_SEND_ACK;
  client.println("OK:CONFIG");
}


void handleActivityMessage(String request)
{
  String payload = request.substring(9);

  Serial.println("Start/Stop received");

    if (payload == "START") 
    {
      Serial.println("STARTING");
      campaign_ongoing = true;
      blnStart = true;
    }
    else if (payload == "STOP") 
    {
      Serial.println("STOPPING");
      blnStop = true;
      campaign_ongoing = false;
      for (int i = 0; i < REQ_MSG; i++)
        exchanged_msg[i] = false;
      Serial.println(" moving to STATE_STOP");
    }
    else 
    {
      Serial.println("Start/Stop: Invalid payload length");
    }
}

void printCurrentNet() {
  Serial.print("SSID: ");
  Serial.println(WiFi.SSID());

  byte bssid[6];
  WiFi.BSSID(bssid);
  Serial.print("BSSID: ");
  printMacAddress(bssid);

  long rssi = WiFi.RSSI();
  Serial.print("signal strength (RSSI): ");
  Serial.println(rssi);

  byte encryption = WiFi.encryptionType();
  Serial.print("Encryption Type: ");
  Serial.println(encryption, HEX);
  Serial.println();
}

void printWifiData() {
  IPAddress ip = WiFi.localIP();
  Serial.print("IP Address: ");
  Serial.println(ip);

  byte mac[6];
  WiFi.macAddress(mac);
  Serial.print("MAC address: ");
  printMacAddress(mac);
}

void printMacAddress(byte mac[]) {
  for (int i = 5; i >= 0; i--) {
    if (mac[i] < 16) Serial.print("0");
    Serial.print(mac[i], HEX);
    if (i > 0) Serial.print(":");
  }
  Serial.println();
}

////////////////////////////////////////////////////////////////////////////////////////

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
  
    //Serial.print("Magnetic field sample rate = ");
    //Serial.print(IMU.magneticFieldSampleRate());
    //Serial.println(" Hz");
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
  if (batteryPowered) {
    BLE.setAdvertisedService(bleBatteryService);
    bleBatteryService.addCharacteristic(batteryLevelCharacteristic);
    BLE.addService(bleBatteryService);

    // First value is available immediately after boot.
    refreshBatteryLevel();
    lastSampleTime = millis();
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
  Serial.println("Advertise BLE STARTED");
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

// Callback functions
void connect_callback(BLEDevice dev) {
  Serial.println("BLE client connected");
  Serial.print("Client address: ");
  Serial.println(dev.address());

  if (batteryPowered) {
    refreshBatteryLevel();
  }
}

void disconnect_callback(BLEDevice dev) {
  Serial.println("BLE client disconnected");
  Serial.print("Client address: ");
  Serial.println(dev.address());
}



void sendACK_OK()
{
  if(comm_mode == MODE_BLE)
  {
    uint16_t payload = ACK_OK;
    ackCharacteristic.writeValue((uint8_t*)&payload, sizeof(payload));
  }
  else if(comm_mode == MODE_WIFI)
  {
    client.println("ACK_OK");
  }

  Serial.println("Sent ACK");
  exchanged_msg[MSG_ACK] = true;
  changestate = true;
}

void sendACK_KO(){

  if(comm_mode == MODE_BLE)
  {
    uint16_t payload = ACK_KO;
    ackCharacteristic.writeValue((uint8_t*)&payload, sizeof(payload));
  }
  else if(comm_mode == MODE_WIFI)
  {
    client.println("ACK_KO");
  }
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
  const uint8_t* data=chr.value(); uint16_t len=chr.valueLength();
  if(len!=CONFIGURATION_HEX_LEN)return;

  campaign_settings.sampling_frequency=data[0];
  campaign_settings.mode=data[1];
  campaign_settings.window_size=((uint16_t)data[3]<<8)|data[2];
  campaign_settings.step_size=((uint16_t)data[5]<<8)|data[4];

  bool okFreq=campaign_settings.sampling_frequency>0 &&
              campaign_settings.sampling_frequency<=MAX_IMU_SAMPLING_FREQUENCY;
  bool okMode=campaign_settings.mode==CAMPAIGN_RAW ||
              campaign_settings.mode==CAMPAIGN_FEATURES ||
              campaign_settings.mode==CAMPAIGN_QUAT;
  bool okPrep=true;
  if(campaign_settings.mode==CAMPAIGN_FEATURES)
    okPrep=campaign_settings.window_size>0 &&
           campaign_settings.step_size>0 &&
           campaign_settings.step_size<=campaign_settings.window_size;
  if(!okFreq||!okMode||!okPrep)return;

  campaign_settings.interval=(SAMPL_FREQ_ADJ*1000)/campaign_settings.sampling_frequency;
  counter=0;
  if(campaign_settings.mode==CAMPAIGN_FEATURES){
    if(!allocateFeatureBuffers(campaign_settings.window_size))return;
  }else freeFeatureBuffers();

  exchanged_msg[MSG_CAMP]=true;
  imu_state=STATE_SEND_ACK;
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

unsigned long hex4bytes2ulong(const uint8_t* data){
  return ((unsigned long)data[0] << 24) |
          ((unsigned long)data[1] << 16) |
          ((unsigned long)data[2] << 8)  |
          ((unsigned long)data[3]);
}

/* IMU SPECIFIC */

void sampleAndSendBLE(bool blnSend)
{
  datapacket_t payload;
  uint8_t blepayload[28];
  int16_t ax,ay,az,gx,gy,gz;

  IMU.readAccelGyroRaw(ax,ay,az,gx,gy,gz);

  payload.ax=(uint16_t)ax; payload.ay=(uint16_t)ay; payload.az=(uint16_t)az;
  payload.gx=(uint16_t)gx; payload.gy=(uint16_t)gy; payload.gz=(uint16_t)gz;
  payload.mx=0; payload.my=0; payload.mz=0;
  payload.counter=counter;
  payload.timestamp=updateCurrentTimestamp();

  if(blnSend){
    if(comm_mode==MODE_BLE){
      memcpy(blepayload,&payload,payload_size);
      sensorsCharacteristic.writeValue((uint8_t*)&blepayload,sizeof(blepayload),false);
    } else if(comm_mode==MODE_WIFI){
      uint8_t buffer[payload_size];
      memcpy(buffer,&payload,payload_size);
      client.write(buffer,sizeof(buffer));
    }
  }
  counter++;
}

void sampleBattery(bool blnSend) {
  if (!batteryPowered || !blnSend) {
    return;
  }

  unsigned long currentTime = millis();
  if (currentTime - lastSampleTime < BATTERY_SAMPLING_FREQUENCY) {
    return;
  }

  lastSampleTime = currentTime;
  refreshBatteryLevel();
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

uint8_t batteryVoltageToPercentage(float voltage) {
  const float BATTERY_MIN_VOLTAGE = 3.30f;
  const float BATTERY_MAX_VOLTAGE = 4.20f;

  if (voltage <= BATTERY_MIN_VOLTAGE) return 0;
  if (voltage >= BATTERY_MAX_VOLTAGE) return 100;

  float percentage = ((voltage - BATTERY_MIN_VOLTAGE) /
                      (BATTERY_MAX_VOLTAGE - BATTERY_MIN_VOLTAGE)) * 100.0f;
  return (uint8_t)(percentage + 0.5f);
}

uint8_t refreshBatteryLevel() {
  if (!batteryPowered) {
    return 0;
  }

  float batteryVoltage = readBatteryVoltage();
  uint8_t batteryLevel = batteryVoltageToPercentage(batteryVoltage);
  batteryLevelCharacteristic.writeValue(batteryLevel);

  Serial.print("Battery level updated: ");
  Serial.print(batteryLevel);
  Serial.print("% - voltage: ");
  Serial.print(batteryVoltage, 2);
  Serial.println(" V");

  return batteryLevel;
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
  float batteryVoltage = readBatteryVoltage();

  if (usbVoltage > USB_THRESHOLD) {
    return POWER_USB;
  }

  if (batteryVoltage > BATTERY_PRESENT_THRESHOLD) {
    return POWER_BATTERY;
  }

  return POWER_UNKNOWN;
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
  analogReference(AR_INTERNAL1V0);
  delay(10);  // Allow reference to settle
  
  int analogValue = analogRead(BATTERY_PIN);  // BATTERY_PIN is connected to VCC/4
  
  // Calculate VCC voltage
  float vcc = (1.2 * 1024 / analogValue) * 4;
  
  // Restore normal reference
  analogReference(AR_DEFAULT);
  
  return vcc;
}
