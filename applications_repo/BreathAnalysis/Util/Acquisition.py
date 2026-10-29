from . import Utilities
from . import Preprocessing
from . import Dimension_Reduction
from . import Spectrum_Analysis
from . import Processing
import queue

class Acquisition:
    def __init__(self):
        self.__utility = Utilities.Utility()
        self.__chunks_of_data = queue.Queue()
        self.__signals = []
        self.__columns_to_drop = ['nthvalue']
        self.__columns_to_clean = ['DevID', '1','2','3','4','B','C']

    def add_some_raw_data(self,raw_dataframe):
        self.__chunks_of_data.put(raw_dataframe)
        print("Added a chunk, lenght queque:",self.__chunks_of_data.qsize())
        
    def refining_splitting_DataChunk(self,starting_point):
        data = self.__chunks_of_data.get()
        
        data.columns = ['DevID', 'B', 'C', 'nthvalue', '1', '2', '3', '4', 'time_device']
        data = data.reset_index(drop=True)  # reset the indexes order
        
        
        self.__frequency_sampling = 10
        length = len(data)
        
        print("Prendo un chunck di dati")
        print("Il dataset ha", length, "campioni")
        print("Skipping first", starting_point, "data points")
        #print("Stopping analysis at sample", ncycles)
        
        data_refined = self.__utility.refining_raw_data(data, self.__columns_to_drop, self.__columns_to_clean)
        
        data_splitted_for_Id = self.__utility.split_dataframe_IMU(data_refined,'DevID')
        
        for IdDevice in data_splitted_for_Id.keys():
            data_splitted_for_Id[IdDevice].reset_index(drop=True)
            data_splitted_for_Id[IdDevice] = self.__utility.prepare_for_quaternion(data_splitted_for_Id[IdDevice])
            data_splitted_for_Id[IdDevice] = self.__utility.quaternion_transformation(data_splitted_for_Id[IdDevice],starting_point)   
             
        return data_splitted_for_Id
    
    def refining_a_dictionary_of_raw_data(self,starting_point,df_raw_data):
        
        length = sum(df.shape[0] for df in df_raw_data.values())
        print("Prendo un chunck di dati")
        print("Il dataset ha", length, "campioni")
        print("Skipping first", starting_point, "data points")
        data_splitted_for_Id = {}
        
        for IdDevice in df_raw_data.keys():
            
            data_splitted_for_Id[IdDevice] = df_raw_data[IdDevice][df_raw_data[IdDevice].columns[0:4]]#remove time_device
            data_splitted_for_Id[IdDevice] = data_splitted_for_Id[IdDevice][starting_point:]
            #data_splitted_for_Id[IdDevice].fillna(method='bfill', inplace=True)  #Interpolation of missing values (Removes all the NaN)
            data_splitted_for_Id[IdDevice] = data_splitted_for_Id[IdDevice].bfill()

            #data_splitted_for_Id[IdDevice].fillna(method='ffill', inplace=True)
            data_splitted_for_Id[IdDevice] = data_splitted_for_Id[IdDevice].ffill()

            data_splitted_for_Id[IdDevice] = data_splitted_for_Id[IdDevice].reset_index(drop=True)
            
        return data_splitted_for_Id                      
    
    def cuts_excess_data(self,data_splitted_for_Id):
        
        #Calculate final Index and remove excess data
        final_index = min(len(data) for data in data_splitted_for_Id.values())
        
        print("FINAL INDEX: ", final_index)
        
        for IdDevice in data_splitted_for_Id.keys():
            data_splitted_for_Id[IdDevice] = data_splitted_for_Id[IdDevice][:final_index]
            print(IdDevice, " ", data_splitted_for_Id[IdDevice])
            print("LENGTH ", IdDevice, len(data_splitted_for_Id[IdDevice]))     
            
        return data_splitted_for_Id,final_index       
        
    def prepare_other_data_for_the_elaboration(self,data_splitted_for_Id):
        mean_quaternion_splitted_for_ID = {}
        quaternion_arrays_splitted_for_ID = {}
        
        for IdDevice in data_splitted_for_Id.keys():
            mean_quaternion_splitted_for_ID[IdDevice] = self.__utility.calculate_mean_quaternion(data_splitted_for_Id[IdDevice])
            quaternion_arrays_splitted_for_ID[IdDevice] = data_splitted_for_Id[IdDevice].to_numpy()
        
        return mean_quaternion_splitted_for_ID, quaternion_arrays_splitted_for_ID                 
       
        