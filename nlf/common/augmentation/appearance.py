import cv2
import numpy as np
from simplepyutils import FLAGS

import nlf.common.augmentation.color as coloraug
from nlf.common import improc, util
from nlf.common.util import TRAIN
from nlf.common.augmentation import voc_loader
from nlf.common.augmentation.border import augment_border


def augment_appearance(im, learning_phase, occlude_prob, border_value, rng):
    occlusion_rng = util.new_rng(rng)
    color_rng = util.new_rng(rng)
    jpeg_rng = util.new_rng(rng)
    border_rng = util.new_rng(rng)

    if learning_phase == TRAIN or FLAGS.test_aug:
        if occlude_prob > 0:
            occlude_type = str(occlusion_rng.choice(['objects', 'random-erase']))
        else:
            occlude_type = None

        if occlude_type == 'objects':
            # For object occlusion augmentation, do the occlusion first, then the filtering,
            # so that the occluder blends into the image better.
            if occlusion_rng.uniform(0.0, 1.0) < occlude_prob:
                im = object_occlude(im, occlusion_rng, inplace=True)
            if FLAGS.color_aug:
                im = coloraug.augment_color(im, color_rng)
            if FLAGS.jpeg_aug_prob:
                im = jpeg_artifact(im, jpeg_rng)
        elif occlude_type == 'random-erase':
            # For random erasing, do color aug first, to keep the random block distributed
            # uniformly in 0-255, as in the Random Erasing paper
            if FLAGS.color_aug:
                im = coloraug.augment_color(im, color_rng)
            if FLAGS.jpeg_aug_prob:
                im = jpeg_artifact(im, jpeg_rng)
            if occlusion_rng.uniform(0.0, 1.0) < occlude_prob:
                im = random_erase(
                    im, 0, 1 / 3, 0.3, 1.0 / 0.3, occlusion_rng, inplace=True)
        elif occlude_type is None:
            if FLAGS.color_aug:
                im = coloraug.augment_color(im, color_rng)
            if FLAGS.jpeg_aug_prob:
                im = jpeg_artifact(im, jpeg_rng)

        if FLAGS.augment_border_prob and border_value is not None:
            if border_rng.uniform(0.0, 1.0) < FLAGS.augment_border_prob:
                im = augment_border(im, border_value, border_rng)

    return im


def object_occlude(im, rng, inplace=True):
    # Following [Sárándi et al., arxiv:1808.09316, arxiv:1809.04987]
    factor = im.shape[0] / 256
    count = rng.integers(1, 7)  # this was intended as max=7, so should be high=8
    occluders = voc_loader.load_occluders()

    for i in range(count):
        occluder, occ_mask = util.choice(occluders, rng)
        rescale_factor = rng.uniform(0.2, 1.0) * factor * FLAGS.occlude_aug_scale

        occ_mask = improc.resize_by_factor(occ_mask, rescale_factor)
        occluder = improc.resize_by_factor(occluder, rescale_factor)

        center = rng.uniform(0, im.shape[0], size=2)
        im = improc.paste_over(occluder, im, alpha=occ_mask, center=center, inplace=inplace)

    return im


def random_erase(im, area_factor_low, area_factor_high, aspect_low, aspect_high, rng, inplace=True):
    # Following the random erasing paper [Zhong et al., arxiv:1708.04896]
    image_area = FLAGS.proc_side ** 2
    while True:
        occluder_area = (
                rng.uniform(area_factor_low, area_factor_high) *
                image_area * FLAGS.occlude_aug_scale)
        aspect_ratio = rng.uniform(aspect_low, aspect_high)
        height = (occluder_area * aspect_ratio) ** 0.5
        width = (occluder_area / aspect_ratio) ** 0.5
        pt1 = rng.uniform(0, FLAGS.proc_side, size=2)
        pt2 = pt1 + np.array([width, height])
        if np.all(pt2 < FLAGS.proc_side):
            pt1 = pt1.astype(int)
            pt2 = pt2.astype(int)
            if not inplace:
                im = im.copy()
            im[pt1[1]:pt2[1], pt1[0]:pt2[0]] = rng.integers(
                0, 256, size=(pt2[1] - pt1[1], pt2[0] - pt1[0], 3), dtype=im.dtype)
            return im


def jpeg_artifact(im, rng):
    if rng.random() < FLAGS.jpeg_aug_prob:
        quality = rng.integers(15, 60)
        _, im = cv2.imencode('.jpg', im[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, quality])
        im = cv2.imdecode(im, cv2.IMREAD_COLOR)[..., ::-1]
    return im
