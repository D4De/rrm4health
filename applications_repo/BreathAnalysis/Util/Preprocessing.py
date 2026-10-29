from pyquaternion import Quaternion
import pandas as pd
import math

class Preprocessing:
    
    def __init__(self):
        print("Preprocessing created")
        
    def change_reference_quaternion(self,quat_array,Quat_pose,start_window, window_size,ref_array,Ref_pose):
        
        quat_pose_df = pd.DataFrame(columns=['1', '2', '3', '4']) #Dataframe empty with colomns named '1','2', '3','4'
        ref_pose = pd.DataFrame(columns=['1', '2', '3', '4']) #Dataframe empty with colomns named '1','2', '3','4'
        result_pd = pd.DataFrame(columns=['1', '2', '3', '4'])  # signal with the new reference
        
        for i in range(start_window, start_window + window_size):
            # Main QUATERNION COMPUTATION
            quat = Quaternion(quat_array[i]) #quaternion with starting reference
            pose_quat = Quaternion(Quat_pose)  # quaternion (Quat_pose[i] is an array and each element is the average of one component of the quaternion quat) 
            pose_row = quat * pose_quat.conjugate  # quaternion product
            quat_pose_df.loc[i] = [pose_row[0], pose_row[1], pose_row[2], pose_row[3]] #salvo i risultati in un dataframe
            
            # REFERENCE QUATERNION COMPUTATION
            ref_quat = Quaternion(ref_array[i])
            Ref_pose_quat = Quaternion(Ref_pose)  # for quaternion conjugate
            ref_pose_row = ref_quat * Ref_pose_quat.conjugate  # quaternion product
            ref_pose.loc[i] = [ref_pose_row[0], ref_pose_row[1], ref_pose_row[2], ref_pose_row[3]]
            
            #Changing reference
            Ok_quat = Quaternion(quat_pose_df.loc[i].rename_axis().values)
            Ref_Ok_quat = Quaternion(ref_pose.loc[i].rename_axis().values)
            result_row = Ok_quat * Ref_Ok_quat.conjugate  # referred to the reference
            result_pd.loc[i] = [result_row[0], result_row[1], result_row[2], result_row[3]] #output of product --> orientation with respect to unit of reference
            
        # end of the calculation inside the window, interpolation
        interp_T = result_pd.loc[start_window:start_window + window_size].rolling(window_size,
                                                                        min_periods=math.floor(window_size / 2),
                                                                        center=True).mean()
        result_pd = result_pd - interp_T
        
        return result_pd
