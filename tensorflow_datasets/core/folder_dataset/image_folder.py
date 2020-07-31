# coding=utf-8
# Copyright 2020 The TensorFlow Datasets Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Lint as: python3
"""Image Classification Folder datasets."""

import collections
import os
import random
from typing import Dict, List, Tuple

import tensorflow.compat.v2 as tf
from tensorflow_datasets.core import dataset_builder
from tensorflow_datasets.core import dataset_info
from tensorflow_datasets.core import features as features_lib
from tensorflow_datasets.core import splits as split_lib
from tensorflow_datasets.core.utils import version

_SUPPORTED_IMAGE_FORMAT = ('.jpg', '.jpeg', '.png')


_Example = collections.namedtuple('_Example', ['image_path', 'label'])

# Dict of 'split_name'-> `List[_Example]`
SplitExampleDict = Dict[str, List[_Example]]


class ImageFolder(dataset_builder.DatasetBuilder):
  """Generic image classification dataset created from manual directory.

  `ImageFolder` creates a `tf.data.Dataset` reading the original image files.

  The data directory should have the following structure:

  ```
  path/to/image_dir/
    split_name/  # Ex: 'train'
      label1/  # Ex: 'airplane' or '0015'
        xxx.png
        xxy.png
        xxz.png
      label2/
        xxx.png
        xxy.png
        xxz.png
    split_name/  # Ex: 'test'
      ...
  ```

  To use it:

  ```
  builder = tfds.ImageFolder('path/to/image_dir/')
  print(builder.info)  # num examples, labels... are automatically calculated
  ds = builder.as_dataset(split='train', shuffle_files=True)
  tfds.show_examples(ds, builder.info)
  ```

  """

  VERSION = version.Version('1.0.0')

  def __init__(self, root_dir: str):
    super(ImageFolder, self).__init__()
    self._data_dir = root_dir  # Set data_dir to the existing dir.

    # Extract the splits, examples, labels
    root_dir = os.path.expanduser(root_dir)
    self._split_examples, labels = _get_split_label_images(root_dir)

    # Update DatasetInfo labels
    self.info.features['label'].names = sorted(labels)

    # Update DatasetInfo splits
    split_dict = split_lib.SplitDict(self.name)
    for split_name, examples in self._split_examples.items():
      split_dict.add(split_lib.SplitInfo(
          name=split_name,
          shard_lengths=[len(examples)],
      ))
    self.info.update_splits_if_different(split_dict)

  def _info(self) -> dataset_info.DatasetInfo:
    return dataset_info.DatasetInfo(
        builder=self,
        description='Generic image classification dataset.',
        features=features_lib.FeaturesDict({
            'image': features_lib.Image(),
            'label': features_lib.ClassLabel(),
            'image/filename': features_lib.Text(),
        }),
        supervised_keys=('image', 'label'),
    )

  # TODO(tfds): Should restore `-> NoReturn` annotatation for Python 3.6.2+
  def _download_and_prepare(self, **kwargs):  # -> NoReturn:
    raise NotImplementedError(
        'No need to call download_and_prepare function for {}.'.format(
            type(self).__name__))

  def download_and_prepare(self, **kwargs):  # -> NoReturn:
    return self._download_and_prepare()

  def _as_dataset(
      self,
      split,
      shuffle_files=False,
      decoders=None,
      read_config=None) -> tf.data.Dataset:
    """Generate dataset for given split."""
    del read_config  # Unused (automatically created in `DatasetBuilder`)
    if decoders:
      raise NotImplementedError(
          '`decoders` is not supported with {}'.format(type(self).__name__))
    if split not in self.info.splits.keys():
      raise ValueError(
          'Unrecognized split {}. Subsplit API not yet supported for {}. '
          'Split name should be one of {}.'.format(
              split, type(self).__name__, list(self.info.splits.keys())))

    # Extract all labels/images
    image_paths = []
    labels = []
    examples = self._split_examples[split]
    for example in examples:
      image_paths.append(example.image_path)
      labels.append(self.info.features['label'].str2int(example.label))

    # Build the tf.data.Dataset object
    ds = tf.data.Dataset.from_tensor_slices((image_paths, labels))
    if shuffle_files:
      ds = ds.shuffle(len(examples))
    ds = ds.map(_load_example, num_parallel_calls=tf.data.experimental.AUTOTUNE)
    return ds


def _load_example(path: tf.Tensor, label: tf.Tensor) -> Dict[str, tf.Tensor]:
  img = tf.io.read_file(path)
  # Uses `channels` and `expand_animations` to make sure shape=(None, None, 3)
  img = tf.image.decode_image(img, channels=3, expand_animations=False)
  return {
      'image': img,
      'label': tf.cast(label, tf.int64),
      'image/filename': path,
  }


def _get_split_label_images(
    root_dir: str,
) -> Tuple[SplitExampleDict, List[str]]:
  """Extract all label names and associated images.

  This function guarantee that examples are deterministically shuffled
  and labels are sorted.

  Args:
    root_dir: The folder where the `split/label/image.png` are located

  Returns:
    split_examples: Mapping split_names -> List[_Example]
    labels: The list off labels
  """
  split_examples = collections.defaultdict(list)
  labels = set()
  for split_name in sorted(_list_folders(root_dir)):
    split_dir = os.path.join(root_dir, split_name)
    for label_name in sorted(_list_folders(split_dir)):
      labels.add(label_name)
      split_examples[split_name].extend([
          _Example(image_path=image_path, label=label_name)
          for image_path
          in sorted(_list_img_paths(os.path.join(split_dir, label_name)))
      ])

  # Shuffle the images deterministically
  for split_name, examples in split_examples.items():
    rgn = random.Random(split_name)  # Uses different seed for each split
    rgn.shuffle(examples)
  return split_examples, sorted(labels)


def _list_folders(root_dir: str) -> List[str]:
  return [
      f for f in tf.io.gfile.listdir(root_dir)
      if tf.io.gfile.isdir(os.path.join(root_dir, f))
  ]


def _list_img_paths(root_dir: str) -> List[str]:
  return [
      os.path.join(root_dir, f)
      for f in tf.io.gfile.listdir(root_dir)
      if any(f.lower().endswith(ext) for ext in _SUPPORTED_IMAGE_FORMAT)
  ]