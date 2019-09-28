import numpy as np
import cv2
import random
import glob
from matplotlib import pyplot as plt
from PIL import Image
import pandas as pd
from tqdm import tqdm
import sys
import os

from albumentations import (
    Compose, HorizontalFlip, VerticalFlip, CLAHE, RandomRotate90, HueSaturationValue,
    RandomBrightness, RandomContrast, RandomGamma,OneOf,
    ToFloat, ShiftScaleRotate,GridDistortion, ElasticTransform, JpegCompression, HueSaturationValue,
    RGBShift, RandomBrightnessContrast, RandomContrast, Blur, MotionBlur, MedianBlur, GaussNoise,CenterCrop,
    IAAAdditiveGaussianNoise,GaussNoise,Cutout,Rotate
)

sys.path.append('.')
from utils.visualize import image_with_mask_torch, image_with_mask_numpy
from utils.rle_parse import make_mask


def visualize(image, mask, original_image=None, original_mask=None):
    fontsize = 18
    
    if original_image is None and original_mask is None:
        f, ax = plt.subplots(2, 1, figsize=(8, 8))

        ax[0].imshow(image)
        ax[1].imshow(mask)
    else:
        f, ax = plt.subplots(2, 2, figsize=(8, 8))

        ax[0, 0].imshow(original_image)
        ax[0, 0].set_title('Original image', fontsize=fontsize)
        
        ax[1, 0].imshow(original_mask)
        ax[1, 0].set_title('Original mask', fontsize=fontsize)
        
        ax[0, 1].imshow(image)
        ax[0, 1].set_title('Transformed image', fontsize=fontsize)
        
        ax[1, 1].imshow(mask)
        ax[1, 1].set_title('Transformed mask', fontsize=fontsize)

        plt.show()


def data_augmentation(original_image, original_mask):
    """进行样本和掩膜的随机增强
    
    Args:
        original_image: 原始图片
        original_mask: 原始掩膜
    Return:
        image_aug: 增强后的图片
        mask_aug: 增强后的掩膜
    """
    original_height, original_width = original_image.shape[:2]
    augmentations = Compose([
        HorizontalFlip(p=0.4),
        Rotate(limit=15, p=0.4),   
        CenterCrop(p=0.3, height=original_height, width=original_width),
        # 直方图均衡化
        CLAHE(p=0.4),

        # 亮度、对比度
        RandomGamma(gamma_limit=(80, 120), p=0.1),
        RandomBrightnessContrast(p=0.1),
        
        # 模糊
        OneOf([
                MotionBlur(p=0.1),
                MedianBlur(blur_limit=3, p=0.1),
                Blur(blur_limit=3, p=0.1),
            ], p=0.3),
        
        OneOf([
                IAAAdditiveGaussianNoise(),
                GaussNoise(),
            ], p=0.2)
    ])
    
    augmented = augmentations(image=original_image, mask=original_mask)
    image_aug = augmented['image']
    mask_aug = augmented['mask']

    return image_aug, mask_aug


if __name__ == "__main__":
    data_folder = "../datasets/Steel_data"
    df_path = "../datasets/Steel_data/train.csv"

    df = pd.read_csv(df_path)
    # https://www.kaggle.com/amanooo/defect-detection-starter-u-net
    df['ImageId'], df['ClassId'] = zip(*df['ImageId_ClassId'].str.split('_'))
    df['ClassId'] = df['ClassId'].astype(int)
    df = df.pivot(index='ImageId', columns='ClassId', values='EncodedPixels')
    df['defects'] = df.count(axis=1)
    file_names = df.index.tolist()

    for index in range(len(file_names)):
        image_id, mask = make_mask(index, df)
        image_path = os.path.join(data_folder, 'train_images', image_id)
        image = cv2.imread(image_path)
        image_aug, mask_aug = data_augmentation(image, mask)

        image_mask = image_with_mask_numpy(image, mask)['image']
        image_aug_mask = image_with_mask_numpy(image_aug, mask_aug)['image']
        cv2.imshow('image', image_mask)
        cv2.imshow('image_aug', image_aug_mask)
        cv2.waitKey(0)
    pass
