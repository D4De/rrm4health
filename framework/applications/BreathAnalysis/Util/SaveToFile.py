
class SaveToFile:
    def __init__(self):
        pass
        
    # ------------------------------
    # USER SETTERS
    # ------------------------------
    
    def set_path(self,path):
        self.path = path
        
    def set_name_file(self,name):
        self.name = name

    # ------------------------------
    # PUBLIC METHODS
    # ------------------------------
    
    def save_dataframe_to_csv(self,dataframe):
        dataframe.to_csv(self.path + self.name)
    
    def save_string_to_txt(self,string):
        with open(self.path + self.name + ".txt", "w", encoding="utf-8") as file:
            file.write(string)