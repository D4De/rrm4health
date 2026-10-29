#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

#include <stdint.h>
#include <stdbool.h>
#include "nrf_gpio.h"
#include "nrf_saadc.h"

// ======================================================================
// HARDWARE PINS AND CHANNELS
// ======================================================================

// --------- LEDs and Buttons ---------
#define RESPIRHO_LED_PIN       NRF_GPIO_PIN_MAP(0, 4) // P0.04
#define BUTTON_PIN             NRF_GPIO_PIN_MAP(0, 5) // P0.05

// --------- TWI (I2C) ---------
//#define TWI_SCL_PIN            27
//#define TWI_SDA_PIN            26
#define TWI_SCL_PIN NRF_GPIO_PIN_MAP(0, 27)
#define TWI_SDA_PIN NRF_GPIO_PIN_MAP(0, 26)

// --------- Battery & ADC ---------
#define ADC_ON_PIN             NRF_GPIO_PIN_MAP(0, 6)  
#define BATTERY_ADC_INPUT      NRF_SAADC_INPUT_AIN4    // P0.28
#define SAADC_CHANNEL_BATTERY  0

// ======================================================================
// PUBLIC FUNCTION PROTOTYPES
// ======================================================================

/**
 * @brief Initializes the board's hardware peripherals.
 * 
 * Configures the GPIO pins for the LED, sets up the ADC voltage divider 
 * enable pin, and configures the Stop button with an internal pull-up resistor.
 *
 */
void board_init(void);

/**@brief Turns the main board LED on. */
void led_on(void);

/**@brief Turns the main board LED off. */
void led_off(void);

/**@brief Toggles the main board LED state. */
void led_toggle(void);

#endif