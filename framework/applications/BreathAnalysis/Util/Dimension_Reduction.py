from pyquaternion import Quaternion
from sklearn.decomposition import PCA
import pandas as pd
import math

class Dimension_Reduction:

    def __init__(self):
        print("Dimension Reduction created")    
        
    def dimension_reduction_with_pca2(self,dataframe_quaternion,start_window,window_size):
        pca = PCA(n_components=2)
        return pca.fit_transform(dataframe_quaternion.loc[start_window:start_window + window_size])[:,1]
            