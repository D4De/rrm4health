#include "board_config.h"

void board_init(void) {
    nrf_gpio_cfg_output(RESPIRHO_LED_PIN);
    nrf_gpio_pin_clear(RESPIRHO_LED_PIN);

    nrf_gpio_cfg_output(ADC_ON_PIN);
    nrf_gpio_pin_clear(ADC_ON_PIN);
}

void led_on(void) {
    nrf_gpio_pin_set(RESPIRHO_LED_PIN);
}

void led_off(void) {
    nrf_gpio_pin_clear(RESPIRHO_LED_PIN);
}

void led_toggle(void) {
    nrf_gpio_pin_toggle(RESPIRHO_LED_PIN);
}
