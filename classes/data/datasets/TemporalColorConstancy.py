import glob
import os
from typing import Tuple

from classes.data.datasets.BaseTemporalDataset import BaseTemporalDataset


class TemporalColorConstancy(BaseTemporalDataset):

    def __init__(self, mode: str = "train", input_size: Tuple = (224, 224), split_folder: str = "tcc_split"):
        super().__init__(mode, input_size)
        path_to_dataset = os.path.join("dataset", "tcc", "preprocessed", split_folder)
        path_to_data = os.path.join(path_to_dataset, self._data_dir)
        self._paths_to_items = glob.glob(os.path.join(path_to_data, "{}*.npy".format(mode)))
        self._paths_to_items.sort(key=lambda x: int(x.split(mode)[-1][:-4]))
