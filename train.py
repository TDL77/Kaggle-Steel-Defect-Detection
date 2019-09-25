from torch import optim
import torch
import tqdm
from config import get_config
from solver import solver
from torch.utils.tensorboard import SummaryWriter
import datetime
import os
import codecs, json
import time
from models.model import Model
from utils.cal_dice_iou import Meter
from datasets.steel_dataset import provider
from utils.set_seed import seed_torch
import pickle
import random

class TrainVal():
    def __init__(self, config):
        # 加载网络模型
        self.model_name = config.model_name
        self.model = Model(self.model_name).create_model()

        # 加载超参数
        self.lr = config.lr
        self.weight_decay = config.weight_decay
        self.epoch = config.epoch

        # 实例化实现各种子函数的 solver 类
        self.solver = solver(self.model)

        # 加载损失函数
        self.criterion = torch.nn.BCEWithLogitsLoss()

        # 创建保存权重的路径
        self.model_path = os.path.join(config.save_path, config.model_name)
        if not os.path.exists(self.model_path):
            os.makedirs(self.model_path)

        # 保存json文件和初始化tensorboard
        TIMESTAMP = "{0:%Y-%m-%dT%H-%M-%S}".format(datetime.datetime.now())
        self.writer = SummaryWriter(log_dir=os.path.join(self.model_path, TIMESTAMP))
        with codecs.open(self.model_path + '/'+ TIMESTAMP + '.json', 'w', "utf-8") as json_file:
            json.dump({k: v for k, v in config._get_kwargs()}, json_file, ensure_ascii=False)

        self.max_dice_valid = 0

        # 设置随机种子，注意交叉验证部分划分训练集和验证集的时候，要保持种子固定
        self.seed = int(time.time())
        seed_torch(self.seed)
        with open(self.model_path + '/'+ TIMESTAMP + '.pkl','wb') as f:
            pickle.dump({'seed': self.seed}, f, -1)

    def train(self, train_loader, valid_loader, fold):
        ''' 完成模型的训练，保存模型与日志
        Args:
            train_loader: 训练数据的DataLoader
            valid_loader: 验证数据的Dataloader
            fold: 当前跑的是第几折
        '''
        optimizer = optim.Adam(self.model.module.parameters(), self.lr, weight_decay=self.weight_decay)
        lr_scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, self.epoch+10)
        global_step = 0

        for epoch in range(self.epoch):
            epoch += 1
            epoch_loss = 0
            self.model.train(True)

            tbar = tqdm.tqdm(train_loader)
            for i, (images, masks) in enumerate(tbar):
                # 网络的前向传播与反向传播
                masks_predict = self.solver.forward(images)
                loss = self.solver.cal_loss(masks, masks_predict, self.criterion)
                epoch_loss += loss.item()
                self.solver.backword(optimizer, loss)

                # 保存到tensorboard，每一步存储一个
                self.writer.add_scalar('train_loss', loss.item(), global_step+i)

                descript = "Fold: %d, Train Loss: %.7f, lr: %s" % (fold, loss.item(), self.lr)
                tbar.set_description(desc=descript)

            # 每一个epoch完毕之后，执行学习率衰减
            lr_scheduler.step()
            global_step += len(train_loader)

            # Print the log info
            print('Finish Epoch [%d/%d], Average Loss: %.7f' % (epoch, self.epoch, epoch_loss/len(tbar)))

            # 验证模型
            loss_valid, dice_valid, iou_valid = self.validation(valid_loader)
            if dice_valid > self.max_dice_valid: 
                is_best = True
                self.max_dice_valid = dice_valid
            else: is_best = False
            
            state = {
                'epoch': epoch,
                'state_dict': self.model.module.state_dict(),
                'max_dice_valid': self.max_dice_valid,
            }

            self.solver.save_checkpoint(os.path.join(self.model_path, '%s_fold%d.pth' % (self.model_name, fold)), state, is_best)
            self.writer.add_scalar('valid_loss', loss_valid, epoch)
            self.writer.add_scalar('valid_dice', dice_valid, epoch)

    def validation(self, valid_loader):
        ''' 完成模型的验证过程

        Args:
            valid_loader: 验证数据的Dataloader
        '''
        self.model.eval()
        meter = Meter()
        tbar = tqdm.tqdm(valid_loader)
        loss_sum = 0
        
        with torch.no_grad(): 
            for i, (images, masks) in enumerate(tbar):
                # 完成网络的前向传播
                masks_predict = self.solver.forward(images)
                loss = self.solver.cal_loss(masks, masks_predict, self.criterion)
                loss_sum += loss.item()

                meter.update(masks, masks_predict.detach().cpu())

                descript = "Val Loss: {:.7f}".format(loss.item())
                tbar.set_description(desc=descript)
        loss_mean = loss_sum/len(tbar)

        dices, iou = meter.get_metrics()
        dice, dice_neg, dice_pos = dices
        print("IoU: %0.4f | dice: %0.4f | dice_neg: %0.4f | dice_pos: %0.4f" % (iou, dice, dice_neg, dice_pos))
        return loss_mean, dice, iou

class ChooseMinArea():
    def __init__(self, ):
        pass


if __name__ == "__main__":
    config = get_config()
    mean=(0.485, 0.456, 0.406)
    std=(0.229, 0.224, 0.225)
    dataloaders = provider(config.dataset_root, os.path.join(config.dataset_root, 'train.csv'), mean, std, config.batch_size, config.num_workers, config.n_splits)
    train_val = TrainVal(config)
    for fold_index, [train_loader, valid_loader] in enumerate(dataloaders):
        train_val.train(train_loader, valid_loader, fold_index)
