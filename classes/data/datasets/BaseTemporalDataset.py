from __future__ import print_function

import numpy as np
import torch
import torch.utils.data as data

from classes.data.DataAugmenter import DataAugmenter


class BaseTemporalDataset(data.Dataset):

    def __init__(self, mode, input_size):
        self.__mode = mode
        self.__input_size = input_size
        self.__da = DataAugmenter(input_size)
        self._data_dir, self._label_dir = "ndata_seq", "nlabel"
        self._paths_to_items = []

    def __getitem__(self, index: int) -> tuple:
        path_to_sequence = self._paths_to_items[index]
        label_path = path_to_sequence.replace(self._data_dir, self._label_dir)

        img = np.array(np.load(path_to_sequence), dtype='float32')
        illuminant = np.array(np.load(label_path), dtype='float32')
        mimic = torch.from_numpy(self.__da.augment_mimic(img).transpose((0, 3, 1, 2)).copy())

        if self.__mode == "train":
            img, color_bias = self.__da.augment_sequence(img, illuminant)
            color_bias = np.array([[[color_bias[0][0], color_bias[1][1], color_bias[2][2]]]], dtype=np.float32)
            mimic = torch.mul(mimic, torch.from_numpy(color_bias).view(1, 3, 1, 1))
        else:
            img = self.__da.resize_sequence(img)

        img = np.clip(img, 0.0, 255.0) * (1.0 / 255)
        img = self.__da.hwc_chw(self.__da.gamma_correct(self.__da.brg_to_rgb(img)))

        img = torch.from_numpy(img.copy())
        illuminant = torch.from_numpy(illuminant.copy())

        return img, mimic, illuminant, path_to_sequence

    def __len__(self) -> int:
        return len(self._paths_to_items)
