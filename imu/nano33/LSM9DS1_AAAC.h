/*
  This file is part of the Arduino_LSM9DX1 library.
  Copyright (c) 2019 Arduino SA. All rights reserved.

  This library is free software; you can redistribute it and/or
  modify it under the terms of the GNU Lesser General Public
  License as published by the Free Software Foundation; either
  version 2.1 of the License, or (at your option) any later version.

  This library is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
  Lesser General Public License for more details.

  You should have received a copy of the GNU Lesser General Public
  License along with this library; if not, write to the Free Software
  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
*/

#include <Arduino.h>
#include <Wire.h>

class LSM9DS1Class {
  public:
    LSM9DS1Class(TwoWire& wire);
    virtual ~LSM9DS1Class();

    int begin();
    void end();

    // Controls whether a FIFO is continuously filled, or a single reading is stored.
    // Defaults to one-shot.
    void setContinuousMode();
    void setOneShotMode();

    // Accelerometer
    virtual int readAcceleration(float& x, float& y, float& z); // Results are in g (earth gravity).
    virtual int accelerationAvailable(); // Number of samples in the FIFO.
    virtual float accelerationSampleRate(); // Sampling rate of the sensor.
    virtual int16_t readRawAccelX(); //
    virtual int16_t readRawAccelY(); //
    virtual int16_t readRawAccelZ(); //
    virtual int readRawAcceleration(int16_t& x, int16_t& y, int16_t& z); // Read XYZ in one I2C transaction.

    // Gyroscope
    virtual int readGyroscope(float& x, float& y, float& z); // Results are in degrees/second.
    virtual int gyroscopeAvailable(); // Number of samples in the FIFO.
    virtual float gyroscopeSampleRate(); // Sampling rate of the sensor.
    virtual int16_t readRawGyroX(); //
    virtual int16_t readRawGyroY(); //
    virtual int16_t readRawGyroZ(); //
    virtual int readRawGyroscope(int16_t& x, int16_t& y, int16_t& z); // Read XYZ in one I2C transaction.

    // Magnetometer
    virtual int readMagneticField(float& x, float& y, float& z); // Results are in uT (micro Tesla).
    virtual int magneticFieldAvailable(); // Number of samples in the FIFO.
    virtual float magneticFieldSampleRate(); // Sampling rate of the sensor.
    virtual int16_t readRawMagX(); //
    virtual int16_t readRawMagY(); //
    virtual int16_t readRawMagZ(); //
    virtual int readRawMagneticField(int16_t& x, int16_t& y, int16_t& z); // Read XYZ in one I2C transaction.

  private:
    bool continuousMode;
    int readRegister(uint8_t slaveAddress, uint8_t address);
    int readRegisters(uint8_t slaveAddress, uint8_t address, uint8_t* data, size_t length);
    int writeRegister(uint8_t slaveAddress, uint8_t address, uint8_t value);

  private:
    TwoWire* _wire;
};

extern LSM9DS1Class IMU_LSM9DS1;
#undef IMU
#define IMU IMU_LSM9DS1
