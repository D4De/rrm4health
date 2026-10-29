#ifndef LSM6DSO_H
#define LSM6DSO_H

#include "nrf_delay.h"
#include "nrf_drv_gpiote.h"
#include <stdint.h>

// ======================================================================
// MACROS AND DEFINES
// ======================================================================

// --------- Device Addresses & IDs ---------
#define LSM6DSO_ADDRESS_LEN  1
//#define LSM6DSO_ADDRESS 0x6B
#define LSM6DSO_ADDRESS      0x6A
#define LIS2MDL_ADDRESS_LEN  1
#define LIS2MDL_ADDRESS      0x1E

#define LSM6DSO_ID             0x6C
#define LSM6DSO_WHO_AM_I_VALUE 0x6CU
#define LIS2MDL_WHO_AM_I_VALUE 0b01000000
// --------- Configuration Macros ---------
// Output Data Rates (ODR)
#define Hz_12_5 1  
#define Hz_26   2  
#define Hz_52   3  
#define Hz_104  4  
#define Hz_208  5  
#define Hz_416  6 

// Accelerometer Full Scale
#define G_2  0
#define G_4  1
#define G_8  2
#define G_16 3

// Gyroscope Full Scale
#define DPS_125  0
#define DPS_250  1
#define DPS_500  2
#define DPS_1000 3

// Masks and Modes
#define mask_0 0
#define mask_1 0x04
#define mask_2 0x08
#define mask_3 0x0C

#define NORMAL_MODE 0x00
#define HUB_MODE    0x40

// LSM6DSO Register Addresses
#define LSM6DSO_FUNC_CFG_ACCESS      0x01U
#define LSM6DSO_PIN_CTRL             0x02U
#define LSM6DSO_FIFO_CTRL1           0x07U
#define LSM6DSO_FIFO_CTRL2           0x08U
#define LSM6DSO_FIFO_CTRL3           0x09U
#define LSM6DSO_FIFO_CTRL4           0x0AU
#define LSM6DSO_COUNTER_BDR_REG1     0x0BU
#define LSM6DSO_COUNTER_BDR_REG2     0x0CU
#define LSM6DSO_INT1_CTRL            0x0D
#define LSM6DSO_INT2_CTRL            0x0EU
#define LSM6DSO_WHO_AM_I_ID          0x0FU
#define LSM6DSO_CTRL1_XL             0x10U
#define LSM6DSO_CTRL2_G              0x11U
#define LSM6DSO_CTRL3_C              0x12U
#define LSM6DSO_CTRL4_C              0x13U
#define LSM6DSO_CTRL5_C              0x14U
#define LSM6DSO_CTRL6_C              0x15U
#define LSM6DSO_CTRL7_G              0x16U
#define LSM6DSO_CTRL8_XL             0x17U
#define LSM6DSO_CTRL9_XL             0x18U
#define LSM6DSO_CTRL10_C             0x19U
#define LSM6DSO_ALL_INT_SRC          0x1AU
#define LSM6DSO_WAKE_UP_SRC          0x1BU
#define LSM6DSO_TAP_SRC              0x1CU
#define LSM6DSO_D6D_SRC              0x1DU
#define LSM6DSO_STATUS_REG           0x1EU
#define LSM6DSO_STATUS_SPIAUX        0x1EU
#define LSM6DSO_OUT_TEMP_L           0x20U
#define LSM6DSO_OUT_TEMP_H           0x21U
#define LSM6DSO_OUTX_L_G             0x22U
#define LSM6DSO_OUTX_H_G             0x23U
#define LSM6DSO_OUTY_L_G             0x24U
#define LSM6DSO_OUTY_H_G             0x25U
#define LSM6DSO_OUTZ_L_G             0x26U
#define LSM6DSO_OUTZ_H_G             0x27U
#define LSM6DSO_OUTX_L_A             0x28U
#define LSM6DSO_OUTX_H_A             0x29U
#define LSM6DSO_OUTY_L_A             0x2AU
#define LSM6DSO_OUTY_H_A             0x2BU
#define LSM6DSO_OUTZ_L_A             0x2CU
#define LSM6DSO_OUTZ_H_A             0x2DU
#define LSM6DSO_EMB_FUNC_STATUS_MAINPAGE 0x35U
#define LSM6DSO_FSM_STATUS_A_MAINPAGE    0x36U
#define LSM6DSO_FSM_STATUS_B_MAINPAGE    0x37U
#define LSM6DSO_STATUS_MASTER_MAINPAGE   0x39U
#define LSM6DSO_FIFO_STATUS1         0x3AU
#define LSM6DSO_FIFO_STATUS2         0x3B
#define LSM6DSO_TIMESTAMP0           0x40U
#define LSM6DSO_TIMESTAMP1           0x41U
#define LSM6DSO_TIMESTAMP2           0x42U
#define LSM6DSO_TIMESTAMP3           0x43U
#define LSM6DSO_TAP_CFG0             0x56U
#define LSM6DSO_TAP_CFG1             0x57U
#define LSM6DSO_TAP_CFG2             0x58U
#define LSM6DSO_TAP_THS_6D           0x59U
#define LSM6DSO_INT_DUR2             0x5AU
#define LSM6DSO_WAKE_UP_THS          0x5BU
#define LSM6DSO_FREE_FALL            0x5DU
#define LSM6DSO_MD1_CFG              0x5EU
#define LSM6DSO_MD2_CFG              0x5FU
#define LSM6DSO_I3C_BUS_AVB          0x62U
#define LSM6DSO_INTERNAL_FREQ_FINE   0x63U
#define LSM6DSO_INT_OIS              0x6FU
#define LSM6DSO_CTRL1_OIS            0x70U
#define LSM6DSO_CTRL2_OIS            0x71U
#define LSM6DSO_CTRL3_OIS            0x72U
#define LSM6DSO_X_OFS_USR            0x73U
#define LSM6DSO_Y_OFS_USR            0x74U
#define LSM6DSO_Z_OFS_USR            0x75U
#define LSM6DSO_FIFO_DATA_OUT_TAG    0x78U
#define LSM6DSO_FIFO_DATA_OUT_X_L    0x79U
#define LSM6DSO_FIFO_DATA_OUT_X_H    0x7AU
#define LSM6DSO_FIFO_DATA_OUT_Y_L    0x7BU
#define LSM6DSO_FIFO_DATA_OUT_Y_H    0x7CU
#define LSM6DSO_FIFO_DATA_OUT_Z_L    0x7DU
#define LSM6DSO_FIFO_DATA_OUT_Z_H    0x7EU
#define LSM6DSO_PAGE_SEL             0x02U
#define LSM6DSO_EMB_FUNC_EN_A        0x04U
#define LSM6DSO_EMB_FUNC_EN_B        0x05U
#define LSM6DSO_PAGE_ADDRESS         0x08U
#define LSM6DSO_PAGE_VALUE           0x09U
#define LSM6DSO_EMB_FUNC_INT1        0x0AU
#define LSM6DSO_FSM_INT1_A           0x0BU
#define LSM6DSO_FSM_INT1_B           0x0CU
#define LSM6DSO_EMB_FUNC_INT2        0x0EU
#define LSM6DSO_FSM_INT2_A           0x0FU
#define LSM6DSO_FSM_INT2_B           0x10U
#define LSM6DSO_EMB_FUNC_STATUS      0x12U
#define LSM6DSO_FSM_STATUS_A         0x13U
#define LSM6DSO_FSM_STATUS_B         0x14U
#define LSM6DSO_PAGE_RW              0x17U
#define LSM6DSO_EMB_FUNC_FIFO_CFG    0x44U
#define LSM6DSO_FSM_ENABLE_A         0x46U
#define LSM6DSO_FSM_ENABLE_B         0x47U
#define LSM6DSO_FSM_LONG_COUNTER_L   0x48U
#define LSM6DSO_FSM_LONG_COUNTER_H   0x49U
#define LSM6DSO_FSM_LONG_COUNTER_CLEAR 0x4AU
#define LSM6DSO_FSM_OUTS1            0x4CU
#define LSM6DSO_FSM_OUTS2            0x4DU
#define LSM6DSO_FSM_OUTS3            0x4EU
#define LSM6DSO_FSM_OUTS4            0x4FU
#define LSM6DSO_FSM_OUTS5            0x50U
#define LSM6DSO_FSM_OUTS6            0x51U
#define LSM6DSO_FSM_OUTS7            0x52U
#define LSM6DSO_FSM_OUTS8            0x53U
#define LSM6DSO_FSM_OUTS9            0x54U
#define LSM6DSO_FSM_OUTS10           0x55U
#define LSM6DSO_FSM_OUTS11           0x56U
#define LSM6DSO_FSM_OUTS12           0x57U
#define LSM6DSO_FSM_OUTS13           0x58U
#define LSM6DSO_FSM_OUTS14           0x59U
#define LSM6DSO_FSM_OUTS15           0x5AU
#define LSM6DSO_FSM_OUTS16           0x5BU
#define LSM6DSO_EMB_FUNC_ODR_CFG_B   0x5FU
#define LSM6DSO_STEP_COUNTER_L       0x62U
#define LSM6DSO_STEP_COUNTER_H       0x63U
#define LSM6DSO_EMB_FUNC_SRC         0x64U
#define LSM6DSO_EMB_FUNC_INIT_A      0x66U
#define LSM6DSO_EMB_FUNC_INIT_B      0x67U
#define LSM6DSO_MAG_SENSITIVITY_L    0xBAU
#define LSM6DSO_MAG_SENSITIVITY_H    0xBBU
#define LSM6DSO_MAG_OFFX_L           0xC0U
#define LSM6DSO_MAG_OFFX_H           0xC1U
#define LSM6DSO_MAG_OFFY_L           0xC2U
#define LSM6DSO_MAG_OFFY_H           0xC3U
#define LSM6DSO_MAG_OFFZ_L           0xC4U
#define LSM6DSO_MAG_OFFZ_H           0xC5U
#define LSM6DSO_MAG_SI_XX_L          0xC6U
#define LSM6DSO_MAG_SI_XX_H          0xC7U
#define LSM6DSO_MAG_SI_XY_L          0xC8U
#define LSM6DSO_MAG_SI_XY_H          0xC9U
#define LSM6DSO_MAG_SI_XZ_L          0xCAU
#define LSM6DSO_MAG_SI_XZ_H          0xCBU
#define LSM6DSO_MAG_SI_YY_L          0xCCU
#define LSM6DSO_MAG_SI_YY_H          0xCDU
#define LSM6DSO_MAG_SI_YZ_L          0xCEU
#define LSM6DSO_MAG_SI_YZ_H          0xCFU
#define LSM6DSO_MAG_SI_ZZ_L          0xD0U
#define LSM6DSO_MAG_SI_ZZ_H          0xD1U
#define LSM6DSO_MAG_CFG_A            0xD4U
#define LSM6DSO_MAG_CFG_B            0xD5U
#define LSM6DSO_FSM_LC_TIMEOUT_L     0x17AU
#define LSM6DSO_FSM_LC_TIMEOUT_H     0x17BU
#define LSM6DSO_FSM_PROGRAMS         0x17CU
#define LSM6DSO_FSM_START_ADD_L      0x17EU
#define LSM6DSO_FSM_START_ADD_H      0x17FU
#define LSM6DSO_PEDO_CMD_REG         0x183U
#define LSM6DSO_PEDO_DEB_STEPS_CONF  0x184U
#define LSM6DSO_PEDO_SC_DELTAT_L     0x1D0U
#define LSM6DSO_PEDO_SC_DELTAT_H     0x1D1U
#define LSM6DSO_SENSOR_HUB_1         0x02U
#define LSM6DSO_SENSOR_HUB_2         0x03U
#define LSM6DSO_SENSOR_HUB_3         0x04U
#define LSM6DSO_SENSOR_HUB_4         0x05U
#define LSM6DSO_SENSOR_HUB_5         0x06U
#define LSM6DSO_SENSOR_HUB_6         0x07U
#define LSM6DSO_SENSOR_HUB_7         0x08U
#define LSM6DSO_SENSOR_HUB_8         0x09U
#define LSM6DSO_SENSOR_HUB_9         0x0AU
#define LSM6DSO_SENSOR_HUB_10        0x0BU
#define LSM6DSO_SENSOR_HUB_11        0x0CU
#define LSM6DSO_SENSOR_HUB_12        0x0DU
#define LSM6DSO_SENSOR_HUB_13        0x0EU
#define LSM6DSO_SENSOR_HUB_14        0x0FU
#define LSM6DSO_SENSOR_HUB_15        0x10U
#define LSM6DSO_SENSOR_HUB_16        0x11U
#define LSM6DSO_SENSOR_HUB_17        0x12U
#define LSM6DSO_SENSOR_HUB_18        0x13U
#define LSM6DSO_MASTER_CONFIG        0x14U
#define LSM6DSO_SLV0_ADD             0x15U
#define LSM6DSO_SLV0_SUBADD          0x16U
#define LSM6DSO_SLV0_CONFIG          0x17U
#define LSM6DSO_SLV1_ADD             0x18U
#define LSM6DSO_SLV1_SUBADD          0x19U
#define LSM6DSO_SLV1_CONFIG          0x1AU
#define LSM6DSO_SLV2_ADD             0x1BU
#define LSM6DSO_SLV2_SUBADD          0x1CU
#define LSM6DSO_SLV2_CONFIG          0x1DU
#define LSM6DSO_SLV3_ADD             0x1EU
#define LSM6DSO_SLV3_SUBADD          0x1FU
#define LSM6DSO_SLV3_CONFIG          0x20U
#define LSM6DSO_DATAWRITE_SLV0       0x21U
#define LSM6DSO_STATUS_MASTER        0x22U
#define LSM6DSO_START_FSM_ADD        0x0400U

// LIS2MDL Register Addresses
#define LIS2MDL_OFFSET_X_REG_L       0x45U
#define LIS2MDL_OFFSET_X_REG_H       0x46U
#define LIS2MDL_OFFSET_Y_REG_L       0x47U
#define LIS2MDL_OFFSET_Y_REG_H       0x48U
#define LIS2MDL_OFFSET_Z_REG_L       0x49U
#define LIS2MDL_OFFSET_Z_REG_H       0x4AU
#define LIS2MDL_WHO_AM_I_ID          0x4FU
#define LIS2MDL_CFG_REG_A            0x60U
#define LIS2MDL_CFG_REG_B            0x61U
#define LIS2MDL_CFG_REG_C            0x62U
#define LIS2MDL_INT_CRTL_REG         0x63U
#define LIS2MDL_INT_SOURCE_REG       0x64U
#define LIS2MDL_INT_THS_L_REG        0x65U
#define LIS2MDL_INT_THS_H_REG        0x66U
#define LIS2MDL_STATUS_REG           0x67U
#define LIS2MDL_OUTX_L_REG           0x68U
#define LIS2MDL_OUTX_H_REG           0x69U
#define LIS2MDL_OUTY_L_REG           0x6AU
#define LIS2MDL_OUTY_H_REG           0x6BU
#define LIS2MDL_OUTZ_L_REG           0x6CU
#define LIS2MDL_OUTZ_H_REG           0x6DU
#define LIS2MDL_TEMP_OUT_L_REG       0x6EU
#define LIS2MDL_TEMP_OUT_H_REG       0x6FU


// ======================================================================
// TYPEDEFS AND STRUCTURES
// ======================================================================

/**
 * @brief Structure to hold raw 16-bit accelerometer data.
 */
typedef struct {
    int16_t z;
    int16_t y;
    int16_t x;
} accel_values_t;

/**
 * @brief Structure to hold raw 16-bit gyroscope data.
 */
typedef struct {
    int16_t z;
    int16_t y;
    int16_t x;
} gyro_values_t;

/**
 * @brief Structure to hold raw 16-bit magnetometer data.
 */
typedef struct {
    int16_t x;
    int16_t y;
    int16_t z;
} magn_values_t;

// ======================================================================
// PUBLIC FUNCTION PROTOTYPES
// ======================================================================

/**
 * @brief Initializes the TWI (I2C) communication as Master.
 */
void twi_master_init(void);

/**
 * @brief Writes a single byte to an LSM6DSO register.
 *
 * @param[in] register_address Register address to start writing to.
 * @param[in] value Value to write.
 * @return true if successful, false otherwise.
 */
bool lsm6dso_register_write(uint8_t register_address, const uint8_t value);

/**
 * @brief Writes a single byte to an LIS2MDL register.
 *
 * @param[in] value Value to write.
 * @param[in] reg Register address to start writing to.
 * @return true if successful, false otherwise.
 */
bool lis2mdl_register_write(uint8_t value, uint8_t reg);

/**
 * @brief Reads one or more bytes from LSM6DSO registers.
 *
 * @param[in] register_address Starting register address.
 * @param[out] destination Buffer to store the read data.
 * @param[in] number_of_bytes Number of bytes to read.
 * @return true if successful, false otherwise.
 */
bool lsm6dso_register_read(uint8_t register_address, uint8_t *destination, size_t number_of_bytes);

/**
 * @brief Reads one or more bytes from LIS2MDL registers.
 *
 * @param[out] value Buffer to store the read data.
 * @param[in] reg Starting register address.
 * @param[in] number_of_bytes Number of bytes to read.
 * @return true if successful, false otherwise.
 */
bool lis2mdl_register_read(uint8_t* value, uint8_t reg, uint8_t number_of_bytes);

/**
 * @brief Verifies the LSM6DSO product ID.
 *
 * @return true if product ID matches the expected value, false otherwise.
 */
bool lsm6dso_verify_product_id(void);

/**
 * @brief Initializes the LSM6DSO primary sensor.
 *
 * @return true on success, false otherwise.
 */
bool lsm6dso_init(void);

/**
 * @brief Initializes the LSM6DSO accelerometer.
 *
 * @param[in] ODR Output Data Rate.
 * @param[in] XL_sense Accelerometer full-scale setting.
 * @param[out] gravity Pointer to store the calculated gravity scale.
 * @return true on success, false otherwise.
 */
bool lsm6dso_accelerometer_init(int16_t ODR, uint8_t XL_sense, int16_t* gravity);

/**
 * @brief Initializes the LSM6DSO gyroscope.
 *
 * @param[in] ODR Output Data Rate.
 * @param[in] GY_sense Gyroscope full-scale setting.
 * @return true on success, false otherwise.
 */
bool lsm6dso_gyroscope_init(int16_t ODR, uint8_t GY_sense);

/**
 * @brief Reads data from the accelerometer.
 *
 * @param[out] accel_values Pointer to store the struct data.
 * @return true on success, false otherwise.
 */
bool LSM6DSO_ReadAcc(accel_values_t * accel_values);

/**
 * @brief Reads data from the gyroscope.
 *
 * @param[out] gyro_values Pointer to store the struct data.
 * @return true on success, false otherwise.
 */
bool LSM6DSO_ReadGyro(gyro_values_t * gyro_values);

/**
 * @brief Reads data from the magnetometer via the Sensor Hub.
 *
 * @param[out] magn_values Pointer to store the struct data.
 * @return true on success, false otherwise.
 */
bool LSM6DSO_WAIT_AND_READ(magn_values_t * magn_value);
bool LSM6DSO_ReadMagn(magn_values_t * magn_values);

/**
 * @brief Sensor Hub entry and exit functions.
 */
bool LSM6DSO_HUB_ENTER(void);
bool LSM6DSO_HUB_EXIT(void);
bool LSM6DSO_RESET(void);
bool lsm6dso_add_sensor(uint8_t addr, uint8_t reg, uint8_t reads);

/**
 * @brief LIS2MDL initialization and verification functions.
 */
bool lis2mdl_check(void);
bool lis2mdl_reset(void);
bool lis2mdl_init(void); 
bool lis2mdl_init_magnetometer(int16_t ODR); 

#endif