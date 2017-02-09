"""Sub-package containing useful transforms for audio and text data."""
from __future__ import division

import types

import librosa
import numpy as np
import torch


# pylint: disable=R0903, C0111

##################
# Helper Classes #
##################

class _Structure(object):
    # Class variable that specifies expected fields
    _fields = []

    def __init__(self, *args, **kwargs):
        if len(args) != len(self._fields):
            raise TypeError(
                'Expected {} arguments'.format(len(self._fields)))

        # Set the arguments
        for name, value in zip(self._fields, args):
            setattr(self, name, value)

        # Set the additional arguments (if any)
        extra_args = kwargs.keys() - self._fields
        for name in extra_args:
            setattr(self, name, kwargs.pop(name))
        if kwargs:
            raise TypeError(
                'Duplicate values for {}'.format(','.join(kwargs)))


###############################
# General/Abstract Transforms #
###############################

class Transform(object):
    """Abstract base class for a transform.

    All other transforms should subclass it. All subclassses should
    override __call__ and __call__ should expect one argument, the
    data to transform, and return the transformed data.

    Any state variables should be stored internally in the __dict__
    class attribute and accessed through self, e.g., self.some_attr.
    """

    def __call__(self, data):
        raise NotImplementedError


class Compose(Transform):
    """Defines a composition of transforms.

    Data will be processed sequentially through each transform.

    Attributes:
        transforms: A list of Transforms to apply sequentially.
    """

    def __init__(self, transforms, *args):
        """Inits Compose with the specified transforms.

        Args:
            transforms: A transform or iterable of transforms to apply.
            args: Additional transforms to append to the pipeline.
        """
        self.transforms = []
        for item in (transforms, *args):
            try:
                self.transforms.extend(item)
            except TypeError:
                self.transforms.append(item)

    def __len__(self):
        return len(self.transforms)

    def __getitem__(self, key):
        return self.transforms[key]

    def __call__(self, data):
        for transform in self.transforms:
            data = transform(data)
        return data


class ToTensor(Transform):
    """Converts a numpy.ndarray to a torch.*Tensor."""

    def __call__(self, array):
        # pylint: disable=E1101
        return torch.from_numpy(array)
        # pylint: enable=E1101


class ToArray(Transform):
    """Converts a torch.*Tensor to a numpy.ndarray."""

    def __call__(self, tensor):
        return tensor.numpy()


class Lambda(Transform):
    """Applies a lamba as a transform.

    Attributes:
        func: A lambda function to be applied to data.
    """

    def __init__(self, func):
        """Inits Lambda with func."""
        assert isinstance(func, types.LambdaType)
        self.func = func

    def __call__(self, data):
        return self.func(data)


#############################
# Audio-oriented transforms #
#############################

class Resample(_Structure, Transform):
    """Resample a time series from orig_sr to target_sr

       Attributes
       ----------
       orig_sr : number > 0 [scalar]
           original sampling rate of `y`

       target_sr : number > 0 [scalar]
           target sampling rate

       res_type : str
           resample type (see note)

           .. note::
               By default, this uses `resampy`'s high-quality mode
               ('kaiser_best'). If `res_type` is not recognized by
               `resampy.resample`, it then falls back on
               `scikits.samplerate` (if it is installed)

               If both of those fail, it will fall back on
               `scipy.signal.resample`.

               To force use of `scipy.signal.resample`, set
               `res_type='scipy'`.

       fix : bool
           adjust the length of the resampled signal to be of size
           exactly `ceil(target_sr * len(y) / orig_sr)`

       scale : bool
           Scale the resampled signal so that `y` and `y_hat` have
           approximately equal total energy.

       kwargs : additional keyword arguments
           If `fix==True`, additional keyword arguments to pass to
           `librosa.util.fix_length`.

       See Also
       --------
       librosa.util.fix_length
       scipy.signal.resample
       """
    _fields = ['orig_sr', 'target_sr']

    def __call__(self, y):
        """Resample a time series.

        Parameters
        ----------
        y : np.ndarray [shape=(n,) or shape=(2, n)]
        audio time series.  Can be mono or stereo.

        Returns
        -------
        y_hat : np.ndarray [shape=(n * target_sr / orig_sr,)]
        """
        return librosa.resample(y, **self.__dict__)


class STFT(_Structure, Transform):
    """Short-time Fourier transform (STFT)

    Attributes
    ----------
    n_fft : int > 0 [scalar]
        FFT window size

    hop_length : int > 0 [scalar]
        number audio of frames between STFT columns.
        If unspecified, defaults `win_length / 4`.

    win_length  : int <= n_fft [scalar]
        Each frame of audio is windowed by `window()`.
        The window will be of length `win_length` and then padded
        with zeros to match `n_fft`.

        If unspecified, defaults to ``win_length = n_fft``.

    window : None, function, np.ndarray [shape=(n_fft,)]
        - None (default): use an asymmetric Hann window
        - a window function, such as `scipy.signal.hanning`
        - a vector or array of length `n_fft`

    center      : boolean
        - If `True`, the signal `y` is padded so that frame
          `D[:, t]` is centered at `y[t * hop_length]`.
        - If `False`, then `D[:, t]` begins at `y[t * hop_length]`

    dtype       : numeric type
        Complex numeric type for `D`.  Default is 64-bit complex.
    """

    def __call__(self, y):
        """Short-time Fourier transform (STFT).

        Returns a real-valued matrix
        Returns a complex-valued matrix D such that
            `np.abs(D[f, t])` is the magnitude of frequency bin `f`
            at frame `t`

            `np.angle(D[f, t])` is the phase of frequency bin `f`
            at frame `t`

        Parameters
        ----------
        y : np.ndarray [shape=(n,)], real-valued
            the input signal (audio time series)

        Returns
        -------
        D : np.ndarray [shape=(1 + n_fft/2, t), dtype=dtype]
        STFT matrix

        """
        return librosa.stft(y, **self.__dict__)


class PowerSpectrogram(_Structure, Compose):
    """Computes the power spectrogram of an input signal."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # pylint: disable=E1101
        self.transforms = [STFT(*args, **kwargs),
                           Lambda(lambda S: np.square(np.abs(S)))]
        # pylint: enable=E1101

    def __call__(self, y):
        return super().__call__(y)


class LogAmplitude(_Structure, Transform):
    """Returns the log-scaled amplitude of a spectrogram."""

    def __call__(self, S):
        return librosa.logamplitude(S, **self.__dict__)


class LogPowerSpectrogram(_Structure, Compose):
    """Computes the log-power spectrogram of an input signal."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transforms = [
            PowerSpectrogram(*args, **kwargs),
            LogAmplitude(*args, **kwargs)
        ]


class MelSpectrogram(_Structure):
    """Computes the Mel-scaled power spectrogram of an input signal."""

    def __call__(self, data):
        return librosa.feature.melspectrogram(y=data, **self.__dict__)


class LogMelSpectrogram(_Structure, Compose):
    """Computes the log-power Mel spectrogram of an input signal."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transforms = [
            MelSpectrogram(*args, **kwargs),
            LogAmplitude(*args, **kwargs)
        ]


class MFCC(_Structure, Transform):
    """Computes the mel-frequency cepstral coefficients of an input signal."""

    def __call__(self, y):
        return librosa.feature.mfcc(y, **self.__dict__)


class StackMemory(_Structure, Transform):
    """Short-term history embedding.

    Vertically concatenate a data vector or matrix with delayed
    copies of itself.
    """

    def __call__(self, data):
        return librosa.feature.stack_memory(data, **self.__dict__)


class Delta(_Structure, Transform):
    _fields = ['']
    """Compute delta features."""

    def __call__(self, data):
        raise NotImplementedError



class InjectNoise(_Structure, Transform):
    """Adds noise to an input signal with some probability and some SNR."""


############################
# Text-Oriented Transforms #
############################


class CharToInt(Transform):
    """Maps a string or other iterable, character-wise, to integer labels.

    Attributes:
        char_to_index: A dictionary containing character keys and
        integer values.

    """

    def __init__(self, char_to_index):
        self.char_to_index = char_to_index

    def __call__(self, data):
        return [int_ for int_ in map(self.char_to_index, data)
                if int_ is not None]