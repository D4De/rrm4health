#include <stdbool.h>
#include <stdint.h>
#include "nrf_drv_twi.h"
#include "lsm6dso.h"
#include "nrf_delay.h"
#include "nrf_gpio.h"
#include "app_error.h"
#include "nrfx_twi.h"

#include "nrf_log.h"
#include "nrf_log_ctrl.h"
#include "nrf_log_default_backends.h"

// ======================================================================
// LOCAL VARIABLES AND MACROS
// ======================================================================
#define TWI_SCL_M           27
#define TWI_SDA_M           26
#define TWI_INSTANCE_ID     1   

static volatile bool m_xfer_done = false;
static const nrf_drv_twi_t m_twi = NRF_DRV_TWI_INSTANCE(TWI_INSTANCE_ID);

// ======================================================================
// TWI (I2C) INIT AND HANDLER
// ======================================================================

/**@brief TWI event handler. Updates the global flag on completion.
 * @param[in] p_event   Pointer to the TWI event.
 * @param[in] p_context General purpose pointer, unused here.
 */
void twi_handler(nrf_drv_twi_evt_t const * p_event, void * p_context)
{
    switch (p_event->type)
    {
        case NRF_DRV_TWI_EVT_DONE:
            m_xfer_done = true;
            break;

        case NRF_DRV_TWI_EVT_ADDRESS_NACK:
            NRF_LOG_ERROR("TWI: ADDRESS NACK (slave 0x%02X non risponde)", p_event->xfer_desc.address);
            m_xfer_done = true;
            break;

        case NRF_DRV_TWI_EVT_DATA_NACK:
            NRF_LOG_ERROR("TWI: DATA NACK");
            m_xfer_done = true;
            break;

        default:
            m_xfer_done = true;
            break;
    }
}

void twi_scan(void)
{
    ret_code_t err_code;
    uint8_t reg = 0x0F;   // WHO_AM_I generico ST
    uint8_t val = 0;

    for (uint8_t addr = 1; addr < 127; addr++)
    {
        err_code = nrf_drv_twi_tx(&m_twi, addr, &reg, 1, true);

        if (err_code == NRF_SUCCESS)
        {
            err_code = nrf_drv_twi_rx(&m_twi, addr, &val, 1);

            if (err_code == NRF_SUCCESS)
            {
                NRF_LOG_INFO("TWI device at 0x%02X, reg 0x0F = 0x%02X", addr, val);
            }
        }
    }
}

void twi_master_init(void)
{
    ret_code_t err_code;

    const nrf_drv_twi_config_t twi_config = {
       .scl                = TWI_SCL_M,
       .sda                = TWI_SDA_M,
       .frequency          = NRF_DRV_TWI_FREQ_100K,
       .interrupt_priority = APP_IRQ_PRIORITY_LOW,
       .clear_bus_init     = true
    };

    NRF_LOG_INFO("Initializing TWI peripheral...");
    err_code = nrf_drv_twi_init(&m_twi, &twi_config, twi_handler, NULL);
    APP_ERROR_CHECK(err_code);
    
    NRF_LOG_INFO("TWI initialized successfully.");
    nrf_drv_twi_enable(&m_twi);
    NRF_LOG_INFO("TWI enabled.");
    //twi_scan();
}

// ======================================================================
// READ / WRITE REGISTERS API
// ======================================================================

bool lsm6dso_register_write(uint8_t register_address, uint8_t value)
{
    ret_code_t err_code;
    uint8_t tx_buf[LSM6DSO_ADDRESS_LEN + 1];

    tx_buf[0] = register_address;
    tx_buf[1] = value;
    m_xfer_done = false;

    err_code = nrf_drv_twi_tx(&m_twi, LSM6DSO_ADDRESS, tx_buf, LSM6DSO_ADDRESS_LEN + 1, false);
    if (err_code != NRF_SUCCESS)
    {
        NRF_LOG_ERROR("TWI TX failed during write: 0x%08X", err_code);
        return false;
    }

    uint32_t timeout = 100000;
    while (!m_xfer_done && --timeout) { }

    if (!m_xfer_done)
    {
        NRF_LOG_ERROR("TWI write timeout");
        return false;
    }

    return true;
}

bool lis2mdl_register_write(uint8_t value, uint8_t reg) 
{
    uint8_t buf = 0;

    LSM6DSO_HUB_ENTER();
    (void)lsm6dso_register_write(LSM6DSO_SLV0_ADD, (LIS2MDL_ADDRESS << 1));
    (void)lsm6dso_register_write(LSM6DSO_SLV0_SUBADD, reg);
    (void)lsm6dso_register_write(LSM6DSO_SLV0_CONFIG, 0x00);
    (void)lsm6dso_register_write(LSM6DSO_DATAWRITE_SLV0, value);
    (void)lsm6dso_register_write(LSM6DSO_MASTER_CONFIG, 0x4C);

    while (!(buf & 0b10000000)) 
    {
        lsm6dso_register_read(LSM6DSO_STATUS_MASTER, &buf, 1);
    }
 
    buf = 0; 
    (void)lsm6dso_register_write(LSM6DSO_MASTER_CONFIG, 0x08);
    nrf_delay_ms(10);

    LSM6DSO_HUB_EXIT();
    return true;
}

bool lsm6dso_register_read(uint8_t register_address, uint8_t * destination, size_t number_of_bytes) 
{
    ret_code_t err_code;

    m_xfer_done = false;
    err_code = nrf_drv_twi_tx(&m_twi, LSM6DSO_ADDRESS, &register_address, 1, true);
    APP_ERROR_CHECK(err_code);  

    while (m_xfer_done == false) {}
    if (NRF_SUCCESS != err_code)
    {
        return false;
    }

    m_xfer_done = false;
    err_code = nrf_drv_twi_rx(&m_twi, LSM6DSO_ADDRESS, destination, number_of_bytes);
    APP_ERROR_CHECK(err_code);
    
    while (m_xfer_done == false) {}
    
    if (NRF_SUCCESS != err_code)
    {
        return false;
    }
    
    return true;
}

bool lis2mdl_register_read(uint8_t *value, uint8_t reg, uint8_t number_of_bytes) 
{
    uint8_t buf = 0;
    LSM6DSO_HUB_ENTER();
    
    (void)lsm6dso_register_write(LSM6DSO_SLV0_ADD, (LIS2MDL_ADDRESS << 1) | 0x01U);
    (void)lsm6dso_register_write(LSM6DSO_SLV0_SUBADD, reg);
    (void)lsm6dso_register_write(LSM6DSO_SLV0_CONFIG, 0x01);
    (void)lsm6dso_register_write(LSM6DSO_MASTER_CONFIG, 0x4C);
    
    LSM6DSO_HUB_EXIT();
    lsm6dso_register_read(LSM6DSO_OUTX_H_A, &buf, 1);
    
    buf = 0;
    while (!(buf & 0x01)) 
    {
        lsm6dso_register_read(LSM6DSO_STATUS_REG, &buf, 1);
    }
    
    buf = 0;
    nrf_delay_ms(10);

    while (!(buf & 0x01)) 
    {
        lsm6dso_register_read(LSM6DSO_STATUS_MASTER_MAINPAGE, &buf, 1);
    }

    LSM6DSO_HUB_ENTER();
    lsm6dso_register_write(LSM6DSO_MASTER_CONFIG, 0x00);
    nrf_delay_ms(100);
    lsm6dso_register_read(LSM6DSO_SENSOR_HUB_1, value, number_of_bytes);
    LSM6DSO_HUB_EXIT();

    return true;
}

// ======================================================================
// INITIALIZATIONS
// ======================================================================

bool lsm6dso_verify_product_id(void) 
{
    uint8_t who_am_i; 
    uint8_t func_cfg = 0x00; 
    
    NRF_LOG_INFO("Configuring LSM6DSO function access...");
    lsm6dso_register_write(LSM6DSO_FUNC_CFG_ACCESS, func_cfg);

    NRF_LOG_INFO("Reading LSM6DSO WHO_AM_I register...");
    if (lsm6dso_register_read(LSM6DSO_WHO_AM_I_ID, &who_am_i, 1))
    {
        if (who_am_i != LSM6DSO_WHO_AM_I_VALUE) { return false; }
        else { return true; }
    }
    else { return false; }
}

bool lsm6dso_init(void) 
{ 
    bool transfer_succeeded = true;
    
    transfer_succeeded &= lsm6dso_verify_product_id();
    if(lsm6dso_verify_product_id() == false)
    {
        return false;
    }

    uint8_t Acc_ctrl_reg1_50_Hz = 0x30;
    (void)lsm6dso_register_write(LSM6DSO_CTRL1_XL, Acc_ctrl_reg1_50_Hz); 

    uint8_t Gyr_ctrl_reg1_50_Hz = 0x30;
    (void)lsm6dso_register_write(LSM6DSO_CTRL2_G, Gyr_ctrl_reg1_50_Hz); 

    return transfer_succeeded;
}

bool lsm6dso_accelerometer_init(int16_t ODR, uint8_t XL_sense, int16_t* gravity)
{
    if(lsm6dso_verify_product_id() == false)
    {
        return false;
    }

    uint8_t buffer = 0;

    switch (ODR)
    {
      case Hz_12_5: buffer = 0x10; break;
      case Hz_26:   buffer = 0x20; break;
      case Hz_52:   buffer = 0x30; break;
      case Hz_104:  buffer = 0x40; break;
      case Hz_208:  buffer = 0x50; break;
      case Hz_416:  buffer = 0x60; break;
      default: break;
    }

    switch (XL_sense)
    {
      case G_2:
        buffer |= mask_0;
        *gravity = 16384;
        NRF_LOG_INFO("Accelerometer full-scale: 2G");
        break;
      case G_4:
        buffer |= mask_2;
        NRF_LOG_INFO("Accelerometer full-scale: 4G");
        *gravity = 8192;
        break;
      case G_8:
        buffer |= mask_3;
        NRF_LOG_INFO("Accelerometer full-scale: 8G");
        *gravity = 4096;
        break;
      case G_16:
        buffer |= mask_1;
        NRF_LOG_INFO("Accelerometer full-scale: 16G");
        *gravity = 2048;
        break;
      default: break;
    }
    
    (void)lsm6dso_register_write(LSM6DSO_CTRL1_XL, buffer); 
    return true;
}

bool lsm6dso_gyroscope_init(int16_t ODR, uint8_t GY_sense)
{
    if(lsm6dso_verify_product_id() == false)
    {
        return false;
    }

    uint8_t buffer = 0;

    switch (ODR)
    {
      case Hz_12_5: buffer = 0x10; break;
      case Hz_26:   buffer = 0x20; break;
      case Hz_52:   buffer = 0x30; break;
      case Hz_104:  buffer = 0x40; break;
      case Hz_208:  buffer = 0x50; break;
      case Hz_416:  buffer = 0x60; break;
      default: break;
    }

    switch (GY_sense)
    {
      case DPS_125:
        buffer |= mask_0;
        NRF_LOG_INFO("Gyroscope full-scale: 125 DPS");
        break;
      case DPS_250:
        buffer |= mask_1;
        NRF_LOG_INFO("Gyroscope full-scale: 250 DPS");
        break;
      case DPS_500:
        buffer |= mask_2;
        NRF_LOG_INFO("Gyroscope full-scale: 500 DPS");
        break;
      case DPS_1000:
        buffer |= mask_3;
        NRF_LOG_INFO("Gyroscope full-scale: 1000 DPS");
        break;
      default: break;
    }
    
    (void)lsm6dso_register_write(LSM6DSO_CTRL2_G, buffer); 
    return true;
}


bool LSM6DSO_ReadGyro(gyro_values_t * gyro_values)
{
    uint8_t raw_values[6];
    bool ret = false;    
    
    if(lsm6dso_register_read(LSM6DSO_OUTX_L_G, raw_values, 6) == true)
    {
        gyro_values->x = (int16_t)((raw_values[1] << 8) | raw_values[0]);
        gyro_values->y = (int16_t)((raw_values[3] << 8) | raw_values[2]);
        gyro_values->z = (int16_t)((raw_values[5] << 8) | raw_values[4]);
        ret = true;
    }
    return ret;
}

// ======================================================================
// READ SENSOR DATA
// ======================================================================

bool LSM6DSO_ReadAcc(accel_values_t * accel_values)
{
    uint8_t raw_values[6];
    bool ret = false;    
    
    if(lsm6dso_register_read(LSM6DSO_OUTX_L_A, raw_values, 6) == true)
    {
        accel_values->x = (int16_t)((raw_values[1] << 8) | raw_values[0]);
        accel_values->y = (int16_t)((raw_values[3] << 8) | raw_values[2]);
        accel_values->z = (int16_t)((raw_values[5] << 8) | raw_values[4]);
        ret = true;
    }
    return ret;
}

bool LSM6DSO_WAIT_AND_READ(magn_values_t * magn_values) 
{
    LSM6DSO_HUB_ENTER();

    uint8_t ready = 0;
    uint32_t timeout = 1000;

    do {
        lsm6dso_register_read(LSM6DSO_STATUS_MASTER, &ready, 1);
    } while (!(ready & 0b00000001) && --timeout);

    LSM6DSO_HUB_EXIT();

    if (timeout == 0) {
        NRF_LOG_WARNING("Magnetometer hub timeout");
        return false;
    }

    LSM6DSO_ReadMagn(magn_values);
    return true;
}

bool LSM6DSO_ReadMagn(magn_values_t * magn_values) 
{
    uint8_t raw_values[6];
    bool ret = false;    

    LSM6DSO_HUB_ENTER();    

    if(lsm6dso_register_read(LSM6DSO_SENSOR_HUB_1, raw_values, 6) == true)
    {
        magn_values->x = (int16_t)((raw_values[1] << 8) | raw_values[0]);
        magn_values->y = (int16_t)((raw_values[3] << 8) | raw_values[2]);
        magn_values->z = (int16_t)((raw_values[5] << 8) | raw_values[4]);
        ret = true;
    }

    LSM6DSO_HUB_EXIT();    
    return ret;
}

// ======================================================================
// HUB, RESET AND LIS2MDL CONTROL
// ======================================================================

bool LSM6DSO_HUB_ENTER(void)
{
    lsm6dso_register_write(LSM6DSO_FUNC_CFG_ACCESS, HUB_MODE);
    return true;
}

bool LSM6DSO_HUB_EXIT(void) 
{
    lsm6dso_register_write(LSM6DSO_FUNC_CFG_ACCESS, NORMAL_MODE);
    return true;
}

bool LSM6DSO_RESET(void) 
{
     LSM6DSO_HUB_EXIT();

     (void)lsm6dso_register_write(LSM6DSO_CTRL1_XL, 0x00);
     (void)lsm6dso_register_write(LSM6DSO_CTRL2_G, 0x00);
     (void)lsm6dso_register_write(LSM6DSO_CTRL3_C, 0b10000100);
     nrf_delay_ms(20);

     (void)lsm6dso_register_write(LSM6DSO_CTRL1_XL, 0x00);
     (void)lsm6dso_register_write(LSM6DSO_CTRL2_G, 0x00);
     (void)lsm6dso_register_write(LSM6DSO_CTRL3_C, 0b10000100);
     nrf_delay_ms(20);

     return true;
}

bool lis2mdl_check(void) 
{
    uint8_t value = 0;

    lis2mdl_register_read(&value, LIS2MDL_WHO_AM_I_ID, 1);
    if (value == LIS2MDL_WHO_AM_I_VALUE) { return true; }
    else { return false; }
}

bool lis2mdl_reset(void) 
{
      lis2mdl_register_write(0x60, LIS2MDL_CFG_REG_A);
      lis2mdl_register_write(0x00, LIS2MDL_CFG_REG_A);
      return true;
}

bool lis2mdl_init(void) 
{
      uint8_t cfg_reg_A_50_Hz = 0x08;
      lis2mdl_register_write(cfg_reg_A_50_Hz, LIS2MDL_CFG_REG_A);
      return true;
}

bool lis2mdl_init_magnetometer(int16_t ODR) 
{
    uint8_t buffer = 0;

    switch (ODR)
    {
      case Hz_12_5: buffer = 0x00; break;
      case Hz_26:   buffer = 0x04; break;
      case Hz_52:   buffer = 0x08; break;
      case Hz_104:  buffer = 0x0C; break;
      case Hz_208:  buffer = 0x0C; break;
      case Hz_416:  buffer = 0x0C; break;
      default: break;
    }
    
    lis2mdl_register_write(buffer, LIS2MDL_CFG_REG_A);
    return true;
}

bool lsm6dso_add_sensor(uint8_t addr, uint8_t reg, uint8_t reads) 
{
     LSM6DSO_HUB_ENTER();

     (void)lsm6dso_register_write(LSM6DSO_SLV0_ADD, (addr << 1) + 1);
     (void)lsm6dso_register_write(LSM6DSO_SLV0_SUBADD, reg);
     (void)lsm6dso_register_write(LSM6DSO_SLV0_CONFIG, reads);
     (void)lsm6dso_register_write(LSM6DSO_MASTER_CONFIG, 0x4C);

     LSM6DSO_HUB_EXIT();
    return true;
}


