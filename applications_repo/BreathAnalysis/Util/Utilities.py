import numpy as np
import statistics
class Utility:
    
    def __init__(self):
        print("Refining Data created")
        
    def split_dataframe_IMU(self,dataframe_with_all_payload, attribute_splitting):
        # Automatically extract unique DevID values.
        unique_dev_ids = dataframe_with_all_payload[attribute_splitting].str.extract(r'(\d+)')[0].unique()
        
        # Dictionary to store filtered dataframes.
        data_dict = {}
        
        # Iteration on unique DevIDs and creation of dataframes.
        for dev_id in unique_dev_ids:
            filtered_data = dataframe_with_all_payload[dataframe_with_all_payload[attribute_splitting].str.contains(dev_id)]  # Filter data by DevID
            filtered_data = filtered_data.reset_index(drop=True)  # Reset indexes
            data_dict[dev_id] = filtered_data  # Save to dictionary
        
        return data_dict
    
    #to drop some columns and to clean up the data in the cells where the byte are written like: [0x34]
    def refining_raw_data(self,dataframe_with_all_payload,columns_to_drop,columns_to_clean):
        
        data = dataframe_with_all_payload
        
        for column in columns_to_drop:    
            data = data.drop([column], axis=1)
        
        for column in columns_to_clean:
            data[column] = data[column].astype(str)
            data[column] = data[column].str.replace('[', '')
            data[column] = data[column].str.replace(']', '')
            
        return data    
            
    #prepare the dataframe for transformation into quaternions  
    #dataframe must have as columns ['DevID', 'B', 'C', '1', '2', '3', '4','time_device']
    def prepare_for_quaternion(self,dataframe):
        return dataframe[dataframe.columns[1:7]]#remove DevID and time_device    
    
    def quatconv(self,x):
        if x > 127 and x != np.nan:
            x -= 256
        x /= 127
        return x
    
    #dataframe must have as columns ['B', 'C', '1', '2', '3', '4']
    def quaternion_transformation(self,dataframe,starting_point):
        
        dataframe['B'] = dataframe['B'].apply(int, base=16) #column 'B' reprents battery voltage
        dataframe.loc[dataframe['C'] == 'FF', ['B']] = np.nan
        
        for n in ['1','2','3','4']:
            dataframe[n] = dataframe[n].apply(int, base=16) #Convert from HEX to decimal
            dataframe.loc[dataframe['C'] == 'FF', [n]] = np.nan
            dataframe[n] = dataframe[n].apply(lambda x: self.quatconv(x)) #Convert in the range -1 / 1
            
        dataframe = dataframe.drop(['C'], axis=1)  #the byte identifying the data loss is no longer needed
        dataframe = dataframe[starting_point:]
        dataframe.fillna(method='bfill', inplace=True)  #Interpolation of missing values (Removes all the NaN)
        dataframe.fillna(method='ffill', inplace=True)
        dataframe = dataframe.reset_index(drop=True)
        return dataframe
    
    def calculate_mean_quaternion(self,quaternion_dataframe):
        return [statistics.mean(quaternion_dataframe.iloc[:, 0]), #array in which each element is the mean of a certain component of the thoracic quaternion
                    statistics.mean(quaternion_dataframe.iloc[:, 1]),
                    statistics.mean(quaternion_dataframe.iloc[:, 2]),
                    statistics.mean(quaternion_dataframe.iloc[:, 3])]
    
    #dataframe must have as columns ['B', '1', '2', '3', '4']
    def quatDataframe_to_array(self,dataframe):
        return dataframe.iloc[:, 1:5].rename_axis().values  #Array containing only the 4 components of the quaternion            