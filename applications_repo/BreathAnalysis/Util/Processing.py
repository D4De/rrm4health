
import numpy as np
import scipy.signal

class Processing:
    
    def __init__(self):
        print("Processing created")
    
    def detect_MAXIMA_MINIMA(self,Signal_Fuse,f,pxx,lowThreshold,f_threshold_max,f_threshold_min,frequency_sampling,start_window,window_size,nameSignal):
        try:
            Signal_T = Signal_Fuse
            start_T = np.where(f > lowThreshold)[0][0] - 1
            end_T = np.where(f > f_threshold_max)[0][0]
            fBmax_T = max(pxx[start_T:end_T])
            fBI_T = np.where(pxx[start_T:end_T] == fBmax_T)[0][0]
            fBspectrum_T = f[fBI_T + start_T]
            f1 = max(f_threshold_min, fBspectrum_T - 0.4)
            f2 = min(fBspectrum_T + 0.4, f_threshold_max)
            ft_pl = f2
            Wn_pl = ft_pl / (frequency_sampling / 2)
            b, a = scipy.signal.butter(1, 0.15, 'lowpass')
            lowfilt_T = scipy.signal.filtfilt(b, a, np.ravel(Signal_T))
            ft_ph = f1
            Wn_ph = ft_ph / (frequency_sampling / 2)
            b, a = scipy.signal.butter(1, Wn_ph,
                                        'highpass')  # high pass filter (the result is the bandpass filtered version)
            bpfilt_T = scipy.signal.filtfilt(b, a, lowfilt_T)
            if fBspectrum_T * 60 < 12:
                perc_T = 15
                distance_T = 35  # min peak distance of 35 frames corresponds to a respiratory rate of 17 resp/min
                SgolayWindow = 15
            elif 12 < fBspectrum_T * 60 < 20:
                perc_T = 8
                distance_T = 20  # min peak distance of 20 frames corresponds to a respiratory rate of 30 resp/min
                SgolayWindow = 11
            else:
                perc_T = 5
                distance_T = 9  # min peak distance of 12 frames corresponds to a frequency rate of 50 resp/min
                SgolayWindow = 9
            SmoothSmoothT = scipy.signal.savgol_filter(bpfilt_T, SgolayWindow, 3)
            diff_SST = max(SmoothSmoothT[start_window:start_window + window_size]) - min(SmoothSmoothT[start_window:start_window + window_size])
            thr_SST = diff_SST * perc_T / 100
            Max_Ind_T = scipy.signal.find_peaks(SmoothSmoothT, distance=12, prominence=thr_SST) #distance=distance_T, prominence=thr_SST
            Max_Ind_T = Max_Ind_T[0]
            Maxima_T = SmoothSmoothT[Max_Ind_T]
            Min_Ind_T, Minima_T = [], []
            for i in range(len(Max_Ind_T) - 1):
                min_value = min(SmoothSmoothT[Max_Ind_T[i]:Max_Ind_T[i + 1]])
                Minima_T.append(min_value)
                min_index = np.argmin(SmoothSmoothT[Max_Ind_T[i]:Max_Ind_T[i + 1]]) + Max_Ind_T[i]
                Min_Ind_T.append(min_index)
        except Exception as e:
            print("tor max-min detection error:", e)
        return Max_Ind_T,Min_Ind_T, SmoothSmoothT
    
    def calculate_total_respiratory_signal(self,SmoothSmoothT,SmoothSmoothA,frequency_sampling,start_window,window_size,overlapping,lowThreshold,f_threshold_max):
        try:
            # TOTAL RESPIRATORY SIGNAL
            SmoothSmoothTot = SmoothSmoothT + SmoothSmoothA
            f_Tot, pxx_Tot = scipy.signal.welch(SmoothSmoothTot, window='hamming', fs=frequency_sampling, nperseg=window_size, noverlap=overlapping,
                                                nfft=window_size, detrend=False)  # Power spectral density computation
            start_Tot = np.where(f_Tot > lowThreshold)[0][0] - 1
            end_Tot = np.where(f_Tot > f_threshold_max)[0][0]
            fBmax_Tot = max(pxx_Tot[start_Tot:end_Tot])
            fBI_Tot = np.where(pxx_Tot[start_Tot:end_Tot] == fBmax_Tot)[0][0]
            nmax = np.where(f_Tot > 1)[0][0]
            fBspectrum_Tot = f_Tot[fBI_Tot + start_Tot]
            if fBspectrum_Tot * 60 < 12:
                perc_Tot = 15
                distance_Tot = 35  # min peak distance of 35 frames corresponds to a respiratory rate of 17 resp/min
                SgolayWindow = 15
            elif 12 < fBspectrum_Tot * 60 < 20:
                perc_Tot = 8
                distance_Tot = 20  # min peak distance of 20 frames corresponds to a respiratory rate of 30 resp/min
                SgolayWindow = 11
            else:
                perc_Tot = 5
                distance_Tot = 9  # min peak distance of 12 frames corresponds to a frequency rate of 50 resp/min
                SgolayWindow = 9
            diff_SSTot = max(SmoothSmoothTot[start_window:start_window + window_size]) - min(SmoothSmoothTot[start_window:start_window + window_size])
            thr_SSTot = diff_SSTot * perc_Tot / 100

            Max_Ind_Tot = scipy.signal.find_peaks(SmoothSmoothTot, distance=12, prominence=thr_SSTot) #distance=distance_Tot, prominence=thr_SSTot
            Max_Ind_Tot = Max_Ind_Tot[0]
            Maxima_Tot = SmoothSmoothTot[Max_Ind_Tot]
            Min_Ind_Tot, Minima_Tot = [], []
        except Exception as e:
            print("total resp signal error:", e)     
            
        for i in range(len(Max_Ind_Tot) - 1):
            min_value = min(SmoothSmoothTot[Max_Ind_Tot[i]:Max_Ind_Tot[i + 1]])
            Minima_Tot.append(min_value)
            min_index = np.argmin(SmoothSmoothTot[Max_Ind_Tot[i]:Max_Ind_Tot[i + 1]]) + Max_Ind_Tot[i]
            Min_Ind_Tot.append(min_index)   
        
        return Max_Ind_Tot, Min_Ind_Tot   