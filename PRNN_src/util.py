import os
import math
import sys
from functools import reduce

import torch
import torch.optim as optim
import torch.optim.lr_scheduler as lrs
from torch.nn.modules.module import _addindent


class Checkpoint:
    def __init__(self, config):
        self.global_step = 0
        self.last_epoch = 0
        self.config = config
        self.exp_dir = config.exp_dir
        exp_type = config.data_type

        self.model_dir = os.path.join(self.exp_dir, exp_type, 'model')
        self.log_dir = os.path.join(self.exp_dir, exp_type, 'log')
        self.save_dir = os.path.join(self.exp_dir, exp_type, 'save')
        self.ckpt_dir = os.path.join(self.log_dir, 'ckpt.pt')

        os.makedirs(self.model_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.save_dir, exist_ok=True)

    def step(self):
        self.global_step += 1
        return self.global_step

    def save(self, epoch):
        self.last_epoch = epoch
        save_ckpt = {'global_step': self.global_step,
                     'last_epoch': self.last_epoch}
        torch.save(save_ckpt, self.ckpt_dir)

    def load(self):
        load_ckpt = torch.load(self.ckpt_dir)
        self.global_step = load_ckpt['global_step']
        self.last_epoch = load_ckpt['last_epoch']


def make_optimizer(config, model):
    trainable = filter(lambda x: x.requires_grad, model.parameters())
    kwargs_optimizer = {'lr': config.lr, 'weight_decay': config.weight_decay}

    if config.optimizer == 'sgd':
        optimizer_class = optim.SGD
        kwargs_optimizer['momentum'] = config.momentum
    elif config.optimizer == 'adam':
        optimizer_class = optim.Adam
        kwargs_optimizer['betas'] = config.betas
        kwargs_optimizer['eps'] = config.epsilon
    elif config.optimizer == 'rmsprop':
        optimizer_class = optim.RMSprop
        kwargs_optimizer['eps'] = config.epsilon

    # scheduler
    milestones = list(map(lambda x: int(x), config.decay.split('-')))
    kwargs_scheduler = {'milestones': milestones, 'gamma': config.gamma}
    scheduler_class = lrs.MultiStepLR

    class CustomOptimizer(optimizer_class):
        def __init__(self, *args, **kwargs):
            super(CustomOptimizer, self).__init__(*args, **kwargs)

        def _register_scheduler(self, scheduler_class, **kwargs):
            self.scheduler = scheduler_class(self, **kwargs)

        def save(self, ckpt):
            save_dir = os.path.join(ckpt.model_dir, 'optimizer.pt')
            torch.save(self.state_dict(), save_dir)

        def load(self, ckpt):
            load_dir = os.path.join(ckpt.model_dir, 'optimizer.pt')
            epoch = ckpt.last_epoch
            self.load_state_dict(torch.load(load_dir))
            if epoch > 1:
                for _ in range(epoch): self.scheduler.step()

        def schedule(self):
            self.scheduler.step()

        def get_lr(self):
            return self.scheduler.get_lr()[0]

        def get_last_epoch(self):
            return self.scheduler.last_epoch

    optimizer = CustomOptimizer(trainable, **kwargs_optimizer)
    optimizer._register_scheduler(scheduler_class, **kwargs_scheduler)
    return optimizer


def find_files_by_extensions(root, exts=[]):
    def _has_ext(name):
        if not exts:
            return True
        name = name.lower()
        for ext in exts:
            if name.endswith(ext):
                return True
        return False
    for path, _, files in os.walk(root):
        for name in files:
            if _has_ext(name):
                yield os.path.join(path, name)
