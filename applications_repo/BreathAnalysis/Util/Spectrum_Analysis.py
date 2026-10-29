import numpy as np
import scipy.signal
import statistics

class Spectrum_Analysis:
    
        def __init__(self):
            print("Spectrum Analysis created")
            self.__Fuse = {}
            self.__EstimSmooth = {}
        
        #apply the savgol filter to a pca signal inside a specified window and save the result
        def apply_savgol_filter(self,Id,pca_signal,window_size,overlapping,SgolayWindowPCA):
            if self.__Fuse[Id] is None and self.__EstimSmooth[Id] is None: 
                self.__Fuse[Id] = pca_signal
                self.__EstimSmooth[Id] = scipy.signal.savgol_filter(np.ravel(pca_signal), SgolayWindowPCA, 3)
            else:
                self.__Fuse[Id] = np.append(self.__Fuse[Id], pca_signal[window_size - overlapping:])
                self.__EstimSmooth[Id] = np.append(self.__EstimSmooth[Id], scipy.signal.savgol_filter(np.ravel(pca_signal[window_size - overlapping:]), SgolayWindowPCA, 3))                 
        
        def find_peaks(self,Id,start_window,window_size,overlapping,frequency_sampling,f_threshold_min):
            f = None
            pxx = None
            lowThreshold = None
            try:
                # PEAK DETECTION
                #print("max(",self.__EstimSmooth[Id][start_window:start_window + window_size],")")
                diff = max(self.__EstimSmooth[Id][start_window:start_window + window_size]) - min(self.__EstimSmooth[Id][start_window:start_window + window_size])
                thr = diff * 5 / 100
                Index = scipy.signal.find_peaks(self.__EstimSmooth[Id], distance=6, prominence=thr)
                Index = Index[0]  # ‘peak_heights’ selection
                fStimVec = []
                if len(Index) > 2:  # at least 3 peaks are needed to compute the intrapeak distance
                    for i in range(len(Index) - 1):
                        intrapeak = (Index[i + 1] - Index[i]) / frequency_sampling
                        fstim = 1 / intrapeak
                        fStimVec.append(fstim)
                    fStimMean = statistics.mean(fStimVec)
                    fStimstd = statistics.stdev(fStimVec)
                    lowThreshold = max(f_threshold_min, (fStimMean - fStimstd))  # creation of the thorax threshold
                    #print("lowThreshold_T", lowThreshold_T)
                    f, pxx = scipy.signal.welch(np.ravel(self.__Fuse[Id]), window='hamming', fs=10, nperseg=window_size, noverlap=overlapping,
                                                    nfft=window_size,
                                                    detrend=False)  # %PCA_1 thoracic spectrum (fT is the nomralized frequency vector)
            except Exception as e:
                print("peak detection error:", e)     
            return f, pxx,lowThreshold          
        
        def add_new_signal(self,Id):
            if Id not in self.__Fuse.keys():
                self.__Fuse[Id] = None
                self.__EstimSmooth[Id] = None    
            
        def get_a_fuse(self,Id):
            return self.__Fuse[Id]    
        
        def getEsti(self):
            return self.__EstimSmooth