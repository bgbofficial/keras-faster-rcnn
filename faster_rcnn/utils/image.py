# -*- coding: utf-8 -*-
"""
Created on 2018/12/15 下午5:42

@author: mick.yi

图像处理工具类

"""
import skimage
from skimage import io

import numpy as np
import faster_rcnn.utils.tf_utils as tf_utils


def load_image(image_path):
    """
    加载图像
    :param image_path: 图像路径
    :return: [h,w,3] numpy数组
    """
    """Load the specified image and return a [H,W,3] Numpy array.
    """
    # Load image
    image = io.imread(image_path)
    # If grayscale. Convert to RGB for consistency.
    if image.ndim != 3:
        image = skimage.color.gray2rgb(image)
    # If has an alpha channel, remove it for consistency
    if image.shape[-1] == 4:
        image = image[..., :3]
    return image


def load_image_gt(config, image_info, image_id):
    """Load and return ground truth data for an image (image, mask, bounding boxes).

    augment: (deprecated. Use augmentation instead). If true, apply random
        image augmentation. Currently, only horizontal flipping is offered.
    augmentation: Optional. An imgaug (https://github.com/aleju/imgaug) augmentation.
        For example, passing imgaug.augmenters.Fliplr(0.5) flips images
        right/left 50% of the time.
    use_mini_mask: If False, returns full-size masks that are the same height
        and width as the original image. These can be big, for example
        1024x1024x100 (for 100 instances). Mini masks are smaller, typically,
        224x224 and are generated by extracting the bounding box of the
        object and resizing it to MINI_MASK_SHAPE.

    Returns:
    image: [height, width, 3]
    shape: the original shape of the image before resizing and cropping.
    class_ids: [instance_count] Integer class IDs
    bbox: [instance_count, (y1, x1, y2, x2)]
    mask: [height, width, instance_count]. The height and width are those
        of the image unless use_mini_mask is True, in which case they are
        defined in MINI_MASK_SHAPE.
    """
    # Load image and mask
    image = load_image(image_info['filepath'])
    original_shape = image.shape
    image, window, scale, padding, crop = tf_utils.resize_image(
        image,
        min_dim=config.IMAGE_MIN_DIM,
        min_scale=config.IMAGE_MIN_SCALE,
        max_dim=config.IMAGE_MAX_DIM,
        mode=config.IMAGE_RESIZE_MODE)

    # Bounding boxes. Note that some boxes might be all zeros
    # if the corresponding mask got cropped out.
    # class_ids: [num_instances],bbox: [num_instances, (y1, x1, y2, x2)]
    class_ids, bbox = extract_classids_and_bboxes(image_info['bboxes'])

    # Image meta data
    image_meta = compose_image_meta(image_id, original_shape, image.shape,
                                    window, scale)
    # 调整标注的边框
    bbox = adjust_box(bbox, padding, scale)

    return image, image_meta, class_ids, bbox


def compose_image_meta(image_id, original_image_shape, image_shape,
                       window, scale):
    """Takes attributes of an image and puts them in one 1D array.

    image_id: An int ID of the image. Useful for debugging.
    original_image_shape: [H, W, C] before resizing or padding.
    image_shape: [H, W, C] after resizing and padding
    window: (y1, x1, y2, x2) in pixels. The area of the image where the real
            image is (excluding the padding)
    scale: The scaling factor applied to the original image (float32)
    active_class_ids: List of class_ids available in the dataset from which
        the image came. Useful if training on images from multiple datasets
        where not all classes are present in all datasets.
    """
    meta = np.array(
        [image_id] +  # size=1
        list(original_image_shape) +  # size=3
        list(image_shape) +  # size=3
        list(window) +  # size=4 (y1, x1, y2, x2) in image cooredinates
        [scale]  # size=1
    )
    return meta


def parse_image_meta(meta):
    """Parses an array that contains image attributes to its components.
    See compose_image_meta() for more details.

    meta: [batch, meta length] where meta length depends on NUM_CLASSES

    Returns a dict of the parsed values.
    """
    image_id = meta[:, 0]
    original_image_shape = meta[:, 1:4]
    image_shape = meta[:, 4:7]
    window = meta[:, 7:11]  # (y1, x1, y2, x2) window of image in in pixels
    scale = meta[:, 11]
    return {
        "image_id": image_id.astype(np.int32),
        "original_image_shape": original_image_shape.astype(np.int32),
        "image_shape": image_shape.astype(np.int32),
        "window": window.astype(np.int32),
        "scale": scale.astype(np.float32)
    }


def extract_classids_and_bboxes(boxes_info):
    """Compute bounding boxes from masks.
    mask: [height, width, num_instances]. Mask pixels are either 1 or 0.

    Returns:
        class_ids [num_instances]
        bbox array [num_instances, (y1, x1, y2, x2)].
    """
    boxes = []
    class_ids = []
    for box_info in boxes_info:
        #print(box_info)
        class_ids.append(box_info['class_id'])
        boxes.append([box_info['y1'],
                      box_info['x1'],
                      box_info['y2'],
                      box_info['x2']
                      ])
    #print(class_ids)

    boxes = np.asarray(boxes, dtype=np.int32)
    class_ids = np.asarray(class_ids, dtype=np.int32)
    return class_ids, boxes


def adjust_box(boxes, padding, scale):
    """
    根据填充和缩放因子，调整boxes的值
    :param boxes: [N,(y1,x1,y2,x2)]
    :param padding: [(top_pad, bottom_pad), (left_pad, right_pad), (0, 0)]
    :param scale: 缩放因子
    :return:
    """
    boxes = boxes * scale
    boxes[:, 0::2] = boxes[:, 0::2] + padding[0][0]  # 高度padding
    boxes[:, 1::2] = boxes[:, 1::2] + padding[1][0]  # 宽度padding
    return boxes


def fix_num_pad(np_array, num):
    """
    填充到固定的长度
    :param np_array: numpy数组,
    :param num: 长度
    :return:
    """
    shape = np_array.shape
    #print("np_array.shape:{}".format(shape))
    # 增加tag 维
    pad_width = [(0, 0)] * (len(shape) - 1) + [(0, 1)]
    np_array = np.pad(np_array, pad_width, mode='constant', constant_values=0)
    if shape[0] < num:
        # 第一维后面padding，其余维不变
        pad_width = [(0, num - shape[0])] + [(0, 0)] * (len(shape) - 1)
        np_array = np.pad(np_array, pad_width, mode='constant', constant_values=0)
        if len(shape) >= 3:
            np_array[num - shape[0]:, ..., -1] = -1
        else:
            np_array[num - shape[0]:, -1] = -1

    return np_array