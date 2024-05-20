import argparse
import os

import torch
from torch import optim
from torch.utils import data as data_utils

from ..models.syncnet import SyncNet_color_384 as SyncNet
from ..models.sam import Wav2Lip_384
from ..models.vqdisc import NLayerDiscriminator
from trains import Wav2lip_Dataset, gan_train, load_checkpoint

LAMBDA = 10  # gradient penalty


def wasserstein_loss(y_pred, y_true):
    return torch.mean(y_true * y_pred)

parser = argparse.ArgumentParser(description='Code to train the Wav2Lip model WITH the visual quality discriminator')

parser.add_argument("--data_root", help="Root folder of the preprocessed LRS2 dataset", required=True, type=str)
parser.add_argument('--device', default="cpu")
parser.add_argument('--checkpoint_dir', help='Save checkpoints to this directory', required=True, type=str)
parser.add_argument('--syncnet_path', help='Load the pre-trained Expert discriminator', required=True)
parser.add_argument('--pre_path', help='Resume generator from this checkpoint', default=None, type=str)
parser.add_argument('--disc_checkpoint_path', help='Resume quality disc from this checkpoint', default=None, type=str)

args = parser.parse_args()

global_step = 0
global_epoch = 0
if not torch.cuda.is_available():
    args.device = "cpu"

from hparams import *
img_size=384

syncnet = SyncNet().to(args.device)
for p in syncnet.parameters():
    p.requires_grad = False


if __name__ == "__main__":
    checkpoint_dir = args.checkpoint_dir

    # Dataset and Dataloader setup
    train_dataset = Wav2lip_Dataset(f"{args.data_root}/train.txt", img_size)
    test_dataset = Wav2lip_Dataset(f"{args.data_root}/val.txt", img_size)

    train_data_loader = data_utils.DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True,
        num_workers=1)

    test_data_loader = data_utils.DataLoader(
        test_dataset, batch_size=batch_size,
        num_workers=1)

    # Model
    model = Wav2Lip_384(is_sam=False).to(args.device)
    disc = NLayerDiscriminator().to(args.device)

    print('total trainable params {}'.format(sum(p.numel() for p in model.parameters() if p.requires_grad)))
    print('total DISC trainable params {}'.format(sum(p.numel() for p in disc.parameters() if p.requires_grad)))

    optimizer = optim.Adam([p for p in model.parameters() if p.requires_grad],
                           lr=initial_learning_rate, betas=(0.5, 0.999))
    disc_optimizer = optim.Adam([p for p in disc.parameters() if p.requires_grad],
                                lr=disc_initial_learning_rate, betas=(0.5, 0.999))

    if args.pre_path is not None:
        model, global_epoch, global_step = load_checkpoint(args.pre_path, model, args.device, optimizer)

    if args.disc_checkpoint_path is not None:
        load_checkpoint(args.disc_checkpoint_path, disc, args.device, disc_optimizer)

    load_checkpoint(args.syncnet_path, syncnet, args.device, None)

    if not os.path.exists(checkpoint_dir):
        os.mkdir(checkpoint_dir)

    # Train!
    gan_train(args.device, model, train_data_loader, test_data_loader, optimizer, disc_optimizer, checkpoint_dir,
              syncnet, disc,
              step_interval=1000, epochs=500, start_step=global_step, start_epoch=global_epoch)
