import os
import time

import torch.utils.data
from torch.utils.data import DataLoader

from auxiliary.settings import DEVICE
from auxiliary.utils import log_experiment, print_val_metrics, log_metrics, log_time
from classes.data.datasets.GrayBall import GrayBall
from classes.modules.multiframe.ctccnet.ModelCTCCNet import ModelCTCCNet
from classes.modules.multiframe.ctccnetc4.ModelCTCCNetC4 import ModelCTCCNetC4
from classes.training.Evaluator import Evaluator
from classes.training.LossTracker import LossTracker

MODEL_TYPE = "ctccnet"
NUM_FOLDS = 3
BATCH_SIZE = 16
EPOCHS = 50
LEARNING_RATE = 0.00003
BASE_PATH_TO_PTH_SUBMODULE = os.path.join("trained_models", "gb5", "tccnet")
PATH_TO_LOGS = os.path.join("training", "grayball", "logs")

RELOAD_CHECKPOINT = False
PATH_TO_PTH_CHECKPOINT = os.path.join("trained_models", MODEL_TYPE, "model.pth")

MODELS = {"ctccnet": ModelCTCCNet, "ctccnetc4": ModelCTCCNetC4}


def main():
    evaluator = Evaluator()

    for n in range(NUM_FOLDS):

        path_to_log = os.path.join(PATH_TO_LOGS, "{}_fold_{}_{}".format(MODEL_TYPE, n, time.time()))
        os.makedirs(path_to_log)

        path_to_metrics_log = os.path.join(path_to_log, "metrics.csv")
        path_to_experiment_log = os.path.join(path_to_log, "experiment.json")

        log_experiment(MODEL_TYPE, "fold_{}".format(n), LEARNING_RATE, path_to_experiment_log)

        print("\n Loading data for FOLD {}:".format(n))

        training_set = GrayBall(mode="train", fold=n, num_folds=NUM_FOLDS)
        train_loader = DataLoader(dataset=training_set, batch_size=BATCH_SIZE, shuffle=True, num_workers=8)

        test_set = GrayBall(mode="test", fold=n, num_folds=NUM_FOLDS)
        test_loader = DataLoader(dataset=test_set, batch_size=BATCH_SIZE, num_workers=8)

        training_set_size, test_set_size = len(training_set), len(test_set)
        print("\n TRAINING SET")
        print("\t Size: ..... {}".format(training_set_size))
        print("\t Scenes: ... {}".format(training_set.get_scenes()))
        print("\n TEST SET")
        print("\t Size: ..... {}".format(test_set_size))
        print("\t Scenes: ... {}".format(test_set.get_scenes()))

        model = MODELS[MODEL_TYPE]()

        if RELOAD_CHECKPOINT:
            print('\n Reloading checkpoint - pretrained model stored at: {} \n'.format(PATH_TO_PTH_CHECKPOINT))
            model.load(PATH_TO_PTH_CHECKPOINT)
        else:
            if BASE_PATH_TO_PTH_SUBMODULE != '':
                path_to_pth_submodule = os.path.join(BASE_PATH_TO_PTH_SUBMODULE, "fold_{}".format(n), "model.pth")
                print('\n Loading pretrained submodules stored at: {} \n'.format(path_to_pth_submodule))
                model.load_submodules(path_to_pth_submodule)

        model.print_network()
        model.log_network(path_to_log)

        model.set_optimizer(learning_rate=LEARNING_RATE)

        print('\n Training starts... \n')

        best_val_loss, best_metrics = 100.0, evaluator.get_best_metrics()
        train_l1, train_l2, train_l3, train_mal = LossTracker(), LossTracker(), LossTracker(), LossTracker()
        val_l1, val_l2, val_l3, val_mal = LossTracker(), LossTracker(), LossTracker(), LossTracker()

        for epoch in range(EPOCHS):

            # --- Training ---

            model.train_mode()
            train_l1.reset()
            train_l2.reset()
            train_l3.reset()
            train_mal.reset()
            start = time.time()

            for i, data in enumerate(train_loader):

                model.reset_gradient()

                sequence, mimic, label, file_name = data
                sequence = sequence.unsqueeze(1).to(DEVICE) if len(sequence.shape) == 4 else sequence.to(DEVICE)
                mimic = mimic.to(DEVICE)
                label = label.to(DEVICE)

                o1, o2, o3 = model.predict(sequence, mimic)
                l1, l2, l3, mal = model.compute_loss([o1, o2, o3], label)
                mal.backward()
                model.optimize()

                train_l1.update(l1.item())
                train_l2.update(l2.item())
                train_l3.update(l3.item())
                train_mal.update(mal.item())

                if i % 5 == 0:
                    print("[ Epoch: {}/{} - Batch: {}/{} ] | "
                          "[ Train L1: {:.4f} | Train L2: {:.4f} | Train L3: {:.4f} | Train MAL: {:.4f} ]"
                          .format(epoch, EPOCHS, i, training_set_size, l1.item(), l2.item(), l3.item(), mal.item()))

            train_time = time.time() - start
            log_time(time=train_time, time_type="train", path_to_log=path_to_experiment_log)

            # --- Validation ---

            start = time.time()

            val_l1.reset()
            val_l2.reset()
            val_l3.reset()
            val_mal.reset()

            if epoch % 5 == 0:

                print("\n--------------------------------------------------------------")
                print("\t\t Validation")
                print("--------------------------------------------------------------\n")

                with torch.no_grad():

                    model.evaluation_mode()
                    evaluator.reset_errors()

                    for i, data in enumerate(test_loader):

                        sequence, mimic, label, file_name = data
                        sequence = sequence.unsqueeze(1).to(DEVICE) if len(sequence.shape) == 4 else sequence.to(DEVICE)
                        mimic = mimic.to(DEVICE)
                        label = label.to(DEVICE)

                        o1, o2, o3 = model.predict(sequence, mimic)
                        l1, l2, l3, mal = model.compute_loss([o1, o2, o3], label)
                        val_l1.update(l1.item())
                        val_l2.update(l2.item())
                        val_l3.update(l3.item())
                        val_mal.update(mal.item())
                        evaluator.add_error(l3.item())

                        if i % 5 == 0:
                            print("[ Epoch: {}/{} - Batch: {}/{} ] | "
                                  "[ Val L1: {:.4f} | Val L2: {:.4f} | Val L3: {:.4f} | Val MAL: {:.4f} ]"
                                  .format(epoch, EPOCHS, i, test_set_size, l1.item(), l2.item(), l3.item(), mal.item()))

                print("\n--------------------------------------------------------------\n")

            val_time = time.time() - start
            log_time(time=val_time, time_type="val", path_to_log=path_to_experiment_log)

            metrics = evaluator.compute_metrics()
            print("\n********************************************************************")
            print(" Train Time ... : {:.4f}".format(train_time))
            print(" Train MAL .... : {:.4f}".format(train_mal.avg))
            print(" Train L1 ..... : {:.4f}".format(train_l1.avg))
            print(" Train L2 ..... : {:.4f}".format(train_l2.avg))
            print(" Train L3 ..... : {:.4f}".format(train_l3.avg))
            if val_time > 0.1:
                print("....................................................................")
                print(" Val Time ..... : {:.4f}".format(val_time))
                print(" Val MAL ...... : {:.4f}".format(val_mal.avg))
                print(" Val L1 ....... : {:.4f}".format(val_l1.avg))
                print(" Val L2 ....... : {:.4f}".format(val_l2.avg))
                print(" Val L3 ....... : {:.4f} (Best: {:.4f})".format(val_l3.avg, best_val_loss))
                print("....................................................................")
                print_val_metrics(metrics, best_metrics)
            print("********************************************************************\n")

            if 0 < val_l3.avg < best_val_loss:
                best_val_loss = val_l3.avg
                best_metrics = evaluator.update_best_metrics()
                print("Saving new best model... \n")
                model.save(os.path.join(path_to_log, "model.pth"))

            log_metrics(train_mal.avg, val_mal.avg, metrics, best_metrics, path_to_metrics_log)


if __name__ == '__main__':
    main()
