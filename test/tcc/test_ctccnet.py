import argparse
import os
from time import time, perf_counter

import numpy as np
import pandas as pd
import torch.utils.data
from torch.utils.data import DataLoader

from auxiliary.settings import DEVICE
from auxiliary.utils import print_test_metrics
from classes.data.datasets.TemporalColorConstancy import TemporalColorConstancy
from classes.modules.multiframe.ctccnet.ModelCTCCNet import ModelCTCCNet
from classes.modules.multiframe.ctccnetc4.ModelCTCCNetC4 import ModelCTCCNetC4
from classes.training.Evaluator import Evaluator

"""
Results on the TCC benchmark split (tcc_split):
    * TCCNet    : mean: 1.9944, med: 1.2079, tri: 1.4600, bst: 0.3000, wst: 4.8426, pct: 6.3391
    * CTCCNet   : mean: 1.9505, med: 1.2161, tri: 1.4220, bst: 0.2529, wst: 4.7849, pct: 6.1011
    * CTCCNetC4 : mean: 1.6971, med: 0.9229, tri: 1.1347, bst: 0.2197, wst: 4.3621, pct: 6.0535
"""

MODEL_TYPE = "ctccnet"
DATA_FOLDER = "full_seq"
SPLIT_FOLDER = "tcc_split"
PATH_TO_LOGS = os.path.join("test", "tcc", "logs")

MODELS = {"ctccnet": ModelCTCCNet, "ctccnetc4": ModelCTCCNetC4}


def main(opt):
    model_type = opt.model_type
    data_folder = opt.data_folder
    split_folder = opt.split_folder

    path_to_pth = os.path.join("trained_models", data_folder, model_type, split_folder, "model.pth")
    path_to_log = os.path.join(PATH_TO_LOGS, "{}_{}_{}_{}".format(model_type, data_folder, split_folder, time()))
    os.makedirs(path_to_log)

    eval1, eval2, eval3 = Evaluator(), Evaluator(), Evaluator()
    eval_data = {"file_names": [], "predictions": [], "ground_truths": []}
    inference_times = []

    test_set = TemporalColorConstancy(mode="test", split_folder=split_folder)
    test_loader = DataLoader(test_set, batch_size=1, shuffle=False, num_workers=20)
    print('Test set size: {}'.format(len(test_set)))

    model = MODELS[model_type]()

    print('\n Loading pretrained {} model stored at: {} \n'.format(model_type, path_to_pth))
    model.load(path_to_pth)
    model.evaluation_mode()

    print("\n *** Testing model {} on {}/{} *** \n".format(model_type, data_folder, split_folder))

    with torch.no_grad():
        for i, (seq, mimic, label, file_name) in enumerate(test_loader):
            seq, mimic, label = seq.to(DEVICE), mimic.to(DEVICE), label.to(DEVICE)

            tic = perf_counter()
            o1, o2, o3 = model.predict(seq, mimic)
            toc = perf_counter()
            inference_times.append(toc - tic)

            p1, p2, p3 = o1, torch.mul(o1, o2), torch.mul(torch.mul(o1, o2), o3)
            l1 = model.get_angular_loss(p1, label).item()
            l2 = model.get_angular_loss(p2, label).item()
            l3 = model.get_angular_loss(p3, label).item()

            eval1.add_error(l1)
            eval2.add_error(l2)
            eval3.add_error(l3)

            eval_data["file_names"].append(file_name[0])
            eval_data["predictions"].append(p3.cpu().numpy())
            eval_data["ground_truths"].append(label.cpu().numpy())

            if i % 10 == 0:
                print("Item {}: {} - [ L1: {:.4f} | L2: {:.4f} | L3: {:.4f} ]"
                      .format(i, file_name[0].split(os.sep)[-1], l1, l2, l3))

    print(" \n Average inference time: {:.4f} \n".format(np.mean(inference_times)))

    e1, e2, e3 = eval1.get_errors(), eval2.get_errors(), eval3.get_errors()

    eval_data["errors"] = e3
    metrics1, metrics2, metrics3 = eval1.compute_metrics(), eval2.compute_metrics(), eval3.compute_metrics()
    print_test_metrics((metrics1, metrics2, metrics3))

    pd.DataFrame({k: [v] for k, v in metrics1.items()}).to_csv(os.path.join(path_to_log, "metrics_1.csv"), index=False)
    pd.DataFrame({k: [v] for k, v in metrics2.items()}).to_csv(os.path.join(path_to_log, "metrics_2.csv"), index=False)
    pd.DataFrame({k: [v] for k, v in metrics3.items()}).to_csv(os.path.join(path_to_log, "metrics_3.csv"), index=False)
    pd.DataFrame(eval_data).to_csv(os.path.join(path_to_log, "eval.csv"), index=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_type", type=str, default=MODEL_TYPE)
    parser.add_argument('--data_folder', type=str, default=DATA_FOLDER)
    parser.add_argument('--split_folder', type=str, default=SPLIT_FOLDER)
    parser.add_argument('--plot_losses', type=str, default=PLOT_LOSSES)
    opt = parser.parse_args()
    main(opt)
