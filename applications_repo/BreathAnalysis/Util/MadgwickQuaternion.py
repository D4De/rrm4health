
import math

import numpy as np

lastUpdate = 0
firstUpdate = 0
Now = 0    #used to calculate integration interval                               
q = [1.0, 0.0, 0.0, 0.0]           #vector to hold quaternion
eInt = [0.0, 0.0, 0.0]              #vector to hold integral error for Mahony method

PI = 3.14159265358979323846
GyroMeasError = PI*(60.0 / 180.0)     # gyroscope measurement error in rads/s (start at 60 deg/s), then reduce after ~10 s to 3
beta =0.1

def point_transformation(point):
    
    point["ax"] = int(point["ax"], 16)
    point["ay"] = int(point["ay"], 16)
    point["az"] = int(point["az"], 16)
    point["gx"] = int(point["gx"], 16)
    point["gy"] = int(point["gy"], 16)
    point["gz"] = int(point["gz"], 16)
    point["mx"] = int(point["mx"], 16)
    point["my"] = int(point["my"], 16)
    point["mz"] = int(point["mz"], 16)
    
    return point

def MadgwickQuaternionUpdate( ax,  ay,  az,  gx,  gy,  gz,  mx,  my,  mz, deltat):
 
            q = [1.0, 0.0, 0.0, 0.0];
            #float beta = sqrt(3.0f / 4.0f) * GyroMeasError;  // compute beta
            
            # gyroscope measurement drift in rad/s/s (start at 0.0 deg/s/s)
            GyroMeasDrift = PI * (1.0 / 180.0);
            zeta = math.sqrt(3.0 / 4.0) * GyroMeasDrift;  # compute zeta, the other free parameter in the Madgwick scheme usually set to a small or zero value
# here equal to online resources
#==============================================================================================
            q1 = q[0]
            q2 = q[1]
            q3 = q[2]
            q4 = q[3]   #// short name local variable for readability
 
 
            # Auxiliary variables to avoid repeated arithmetic
            _2q1 = 2.0 * q1;
            _2q2 = 2.0 * q2;
            _2q3 = 2.0 * q3;
            _2q4 = 2.0 * q4;
            _2q1q3 = 2.0 * q1 * q3;
            _2q3q4 = 2.0 * q3 * q4;
            q1q1 = q1 * q1;
            q1q2 = q1 * q2;
            q1q3 = q1 * q3;
            q1q4 = q1 * q4;
            q2q2 = q2 * q2;
            q2q3 = q2 * q3;
            q2q4 = q2 * q4;
            q3q3 = q3 * q3;
            q3q4 = q3 * q4;
            q4q4 = q4 * q4;
 
            # Normalise accelerometer measurement
            norm = math.sqrt(ax * ax + ay * ay + az * az);
            if norm == 0.0:
                return [np.nan,np.nan,np.nan,np.nan]; # handle NaN
            norm = 1.0/norm;
            ax *= norm;
            ay *= norm;
            az *= norm;
 
            # Normalise magnetometer measurement
            norm = math.sqrt(mx * mx + my * my + mz * mz);
            if norm == 0.0:
                return [np.nan,np.nan,np.nan,np.nan]; # handle NaN
            norm = 1.0/norm;
            mx *= norm;
            my *= norm;
            mz *= norm;
 
            #Reference direction of Earth's magnetic field
            _2q1mx = 2.0 * q1 * mx;
            _2q1my = 2.0 * q1 * my;
            _2q1mz = 2.0 * q1 * mz;
            _2q2mx = 2.0 * q2 * mx;
            hx = mx * q1q1 - _2q1my * q4 + _2q1mz * q3 + mx * q2q2 + _2q2 * my * q3 + _2q2 * mz * q4 - mx * q3q3 - mx * q4q4;
            hy = _2q1mx * q4 + my * q1q1 - _2q1mz * q2 + _2q2mx * q3 - my * q2q2 + my * q3q3 + _2q3 * mz * q4 - my * q4q4;
            _2bx = math.sqrt(hx * hx + hy * hy);
            _2bz = -_2q1mx * q3 + _2q1my * q2 + mz * q1q1 + _2q2mx * q4 - mz * q2q2 + _2q3 * my * q4 - mz * q3q3 + mz * q4q4;
            _4bx = 2.0 * _2bx;
            _4bz = 2.0 * _2bz;
            _8bx = 2.0 * _4bx;
            _8bz = 2.0 * _4bz;
            # Gradient decent algorithm corrective step             */
            s1= -_2q3*(2*(q2q4 - q1q3) - ax)    +   _2q2*(2*(q1q2 + q3q4) - ay)   +  -_4bz*q3*(_4bx*(0.5 - q3q3 - q4q4) + _4bz*(q2q4 - q1q3) - mx)   +   (-_4bx*q4+_4bz*q2)*(_4bx*(q2q3 - q1q4) + _4bz*(q1q2 + q3q4) - my)    +   _4bx*q3*(_4bx*(q1q3 + q2q4) + _4bz*(0.5 - q2q2 - q3q3) - mz);
            s2= _2q4*(2*(q2q4 - q1q3) - ax) +   _2q1*(2*(q1q2 + q3q4) - ay) +   -4*q2*(2*(0.5 - q2q2 - q3q3) - az)    +   _4bz*q4*(_4bx*(0.5 - q3q3 - q4q4) + _4bz*(q2q4 - q1q3) - mx)   + (_4bx*q3+_4bz*q1)*(_4bx*(q2q3 - q1q4) + _4bz*(q1q2 + q3q4) - my)   +   (_4bx*q4-_8bz*q2)*(_4bx*(q1q3 + q2q4) + _4bz*(0.5 - q2q2 - q3q3) - mz);             
            s3= -_2q1*(2*(q2q4 - q1q3) - ax)    +     _2q4*(2*(q1q2 + q3q4) - ay)   +   (-4*q3)*(2*(0.5 - q2q2 - q3q3) - az) +   (-_8bx*q3-_4bz*q1)*(_4bx*(0.5 - q3q3 - q4q4) + _4bz*(q2q4 - q1q3) - mx)+(_4bx*q2+_4bz*q4)*(_4bx*(q2q3 - q1q4) + _4bz*(q1q2 + q3q4) - my)+(_4bx*q1-_8bz*q3)*(_4bx*(q1q3 + q2q4) + _4bz*(0.5 - q2q2 - q3q3) - mz);
            s4= _2q2*(2*(q2q4 - q1q3) - ax) +   _2q3*(2*(q1q2 + q3q4) - ay)+(-_8bx*q4+_4bz*q2)*(_4bx*(0.5 - q3q3 - q4q4) + _4bz*(q2q4 - q1q3) - mx)+(-_4bx*q1+_4bz*q3)*(_4bx*(q2q3 - q1q4) + _4bz*(q1q2 + q3q4) - my)+(_4bx*q2)*(_4bx*(q1q3 + q2q4) + _4bz*(0.5 - q2q2 - q3q3) - mz);
            norm = math.sqrt(s1 * s1 + s2 * s2 + s3 * s3 + s4 * s4);    #// normalise step magnitude
            norm = 1.0/norm;
            s1 *= norm;
            s2 *= norm;
            s3 *= norm;
            s4 *= norm;
 
            # Compute rate of change of quaternion
            qDot1 = 0.5 * (-q2 * gx - q3 * gy - q4 * gz) - beta * s1;
            qDot2 = 0.5 * (q1 * gx + q3 * gz - q4 * gy) - beta * s2;
            qDot3 = 0.5 * (q1 * gy - q2 * gz + q4 * gx) - beta * s3;
            qDot4 = 0.5 * (q1 * gz + q2 * gy - q3 * gx) - beta * s4;
 
            # Integrate to yield quaternion
            q1 += qDot1 * deltat;
            q2 += qDot2 * deltat;
            q3 += qDot3 * deltat;
            q4 += qDot4 * deltat;
            norm = math.sqrt(q1 * q1 + q2 * q2 + q3 * q3 + q4 * q4);    # normalise quaternion
            norm = 1.0/norm;
            q[0] = q1 * norm;
            q[1] = q2 * norm;
            q[2] = q3 * norm;
            q[3] = q4 * norm;
            return q
 


        