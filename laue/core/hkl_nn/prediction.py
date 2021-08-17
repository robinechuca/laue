#!/usr/bin/env python3

"""
** Deep learning for HKL classification. **
-------------------------------------------

Now can predict with > 95% accuracy for multi grain Laue Patterns.
If you have model save files; go to cell 45 to load and start prediction
Pros: Impressive speed for prediction; results not dependent on
the statistical descriptor (ex: correlation function or distance measurment).
Cons: Building reliable test data can take few hours
(this will significantly increase for less symmetry crystals).
"""

import os
import pickle
import re

from fast_histogram import histogram1d
import h5py
import numpy as np


__pdoc__ = {"Predictor.__call__": True}


class Predictor:
    """
    Cette classe permet de charger le model
    une bonne fois pour toutes.
    """
    def __init__(self, model_directory):
        """
        Parameters
        ----------
        model_directory : str
            Le chemin du repertoire qui contient les donnees du model.

        Examples
        --------
        >>> from laue.core.hkl_nn.prediction import Predictor
        >>> pred = Predictor("laue/data/Zr02")
        >>>
        """
        def select(reg_expr):
            """Cherche le bon fichier et s'assure qu'il soit unique."""
            files = os.listdir(self.model_directory)
            found = [
                (pred.groups(), os.path.join(self.model_directory, files[i]))
                for i, pred in enumerate(
                    re.search(reg_expr, file)
                    for file in os.listdir(self.model_directory))
                if pred is not None]
            if not found:
                raise FileNotFoundError("Le dossier doit contenir un fichier respectant "
                    f"l'expression reguliere: {reg_expr}")
            if len(found) > 1:
                raise ValueError(f"Seul 1 fichier doit matcher avec {reg_expr}. "
                    f"Or {', '.join(f for _, f in found)} sont candidats.")
            return found.pop()
        
        # Verifications.
        assert isinstance(model_directory, str), ("'model_directory' "
            f"has to be str, not {type(model_directory).__name__}.")
        assert os.path.isdir(model_directory), \
            f"{repr(model_directory)} doit etre un dossier existant."

        self.model_directory = model_directory
        
        # File search.
        (material_1,), hkl_data_path = select(r"^hkl_data_(?P<material>\w+)\.pickle$")
        (material_2,), weights_path = select(r"^my_model_(?P<material>\w+)\.h5$")
        _, angbin_path = select(r"^MOD_grain_classhkl_angbin.npz$")

        if material_1 != material_2:
            raise ValueError("Il y a ambiguite. "
                f"Le materiaux c'est {material_1} ou bien {material_2}?")
        self.material = material_1

        # Load data.
        with open(hkl_data_path, "rb") as hkl_data_file:
            ## TODO: list or not in list?
            self.hkl_all_class = pickle.load(hkl_data_file)[0] # Pourquoi le metre dans une liste de 1 element?
        self.wb = self._read_hdf5(weights_path)
        self.hkl_data = np.load(angbin_path)["arr_0"]
        self.angbins = np.load(angbin_path)["arr_1"]

        self.dict_dp={}
        self.dict_dp['kf_direction']='Z>0'
        self.dict_dp['detectorparameters'] = [70.22, 1039.395, 943.57, 0.7478, 0.07186]
        self.dict_dp['detectordistance'] = 70.22
        self.dict_dp['detectordiameter'] = 0.079856*2048
        self.dict_dp['pixelsize'] = 0.079856
        self.dict_dp['dim'] = 2048

    def _read_hdf5(self, path):
        """Read a specific hdf5 file."""
        weights = []
        keys = []
        with h5py.File(path, "r") as f: # open file
            f.visit(keys.append) # append all keys to list
            for key in keys:
                if ":" in key: # contains data if ':' in key
                    try:
                        weights.append(f[key].value)
                    except AttributeError:
                        weights.append(f[key].__array__())
        return weights

    def _predict(self, x):
        """
        ** Help for ``Predictor.__call__``. **
        """
        softmax = lambda x: (np.exp(x).T / np.sum(np.exp(x).T, axis=0)).T
        # first layer
        l0 = np.dot(x, self.wb[1]) + self.wb[0]
        l0 = np.maximum(0, l0) ## ReLU activation
        # Second layer
        l1 = np.dot(l0, self.wb[3]) + self.wb[2]
        l1 = np.maximum(0, l1) ## ReLU activation
        # Third layer
        l2 = np.dot(l1, self.wb[5]) + self.wb[4]
        l2 = np.maximum(0, l2) ## ReLU activation
        # Output layer
        l3 = np.dot(l2, self.wb[7]) + self.wb[6]
        l3 = softmax(l3) ## output softmax activation
        return l3

    def __call__(self, theta_chi):
        """
        ** Estime les hkl. **

        Parameters
        ----------
        theta_chi : np.ndarray
            La matrice des thetas et des chi.
            shape = (2, n), avec n le nombre de spots.

        Returns
        -------
        hkl
            Le vecteur des indices hkl
        score
            Le vecteur des fiabilitees.

        Examples
        --------
        >>> import numpy as np
        >>> from laue.core.hkl_nn.prediction import Predictor
        >>> pred = Predictor("laue/data/Zr02")
        >>> theta_chi = np.array(
        ...   [[ 2.52627945e+01,  2.60926781e+01,  2.65539875e+01,
        ...      2.81886940e+01,  2.88142796e+01,  2.92087307e+01,
        ...      3.04267445e+01,  3.20891838e+01,  3.23967743e+01,
        ...      3.43747025e+01,  3.50725060e+01,  3.51420059e+01,
        ...      3.53640709e+01,  3.66132927e+01,  3.71793442e+01,
        ...      3.78125343e+01,  3.82845306e+01,  3.89372597e+01,
        ...      3.97087402e+01,  4.00737114e+01,  4.07332764e+01,
        ...      4.12437706e+01,  4.04045906e+01,  4.12707405e+01,
        ...      4.20407639e+01,  4.40923157e+01,  4.43046799e+01,
        ...      4.46586914e+01,  4.49168205e+01,  4.54237938e+01,
        ...      4.57435112e+01,  4.64431877e+01,  4.68662910e+01,
        ...      4.70701141e+01,  4.75698853e+01,  4.77383308e+01,
        ...      4.84347076e+01,  4.83345680e+01,  4.82600441e+01,
        ...      4.83319550e+01,  4.89955254e+01,  4.98372574e+01,
        ...      4.80468826e+01,  4.91234589e+01,  5.12316246e+01,
        ...      5.14579887e+01,  5.48247643e+01,  5.42389297e+01,
        ...      5.50067596e+01,  5.47498512e+01,  5.53464012e+01,
        ...      5.44665947e+01,  5.51647453e+01,  5.69880180e+01,
        ...      5.69231071e+01,  5.71547623e+01,  5.59031296e+01,
        ...      5.65157928e+01,  5.54328194e+01,  5.79304810e+01,
        ...      5.83737488e+01,  5.91063004e+01,  5.93900108e+01,
        ...      5.98970032e+01,  5.77238159e+01,  5.97812843e+01,
        ...      5.84865570e+01,  6.03050117e+01,  6.24293098e+01,
        ...      6.18709679e+01,  6.22257271e+01,  6.39516373e+01,
        ...      6.19101753e+01,  6.25465889e+01,  6.08266754e+01,
        ...      6.68958588e+01,  6.72588577e+01,  6.76704407e+01],
        ...    [-2.53227158e+01, -2.17357197e+01,  2.34524479e+01,
        ...      7.92672694e-01, -1.83965931e+01,  2.00298729e+01,
        ...      7.78525651e-01, -1.39836121e+01,  1.55002489e+01,
        ...     -3.47049446e+01,  3.63148613e+01, -9.30009365e+00,
        ...      1.07037458e+01, -2.74188271e+01,  2.88973942e+01,
        ...     -2.24778461e+01,  2.38802395e+01, -3.84828644e+01,
        ...      4.00165977e+01, -3.23755569e+01,  3.37935753e+01,
        ...     -4.06398621e+01,  6.06966138e-01,  2.91247730e+01,
        ...      4.21363029e+01, -9.69736004e+00,  1.07738695e+01,
        ...     -1.17179070e+01,  1.27956800e+01, -1.47250223e+01,
        ...      1.57742653e+01, -1.95509968e+01,  2.06181507e+01,
        ...     -2.32521973e+01,  2.43160992e+01, -2.84838123e+01,
        ...      4.39006448e-01,  2.95768604e+01, -3.62519379e+01,
        ...     -3.96765099e+01,  3.74329453e+01,  3.96892816e-01,
        ...     -4.83194771e+01,  4.09185829e+01, -1.01135015e+01,
        ...      1.08719740e+01,  2.61049420e-01, -2.40735455e+01,
        ...     -1.55187674e+01,  2.47712955e+01,  1.60778942e+01,
        ...     -3.42320824e+01,  3.51054649e+01,  1.88722670e-01,
        ...     -1.05438442e+01,  1.09418879e+01, -2.96021423e+01,
        ...      3.03011723e+01, -4.09050407e+01, -2.08004246e+01,
        ...      2.12467175e+01, -1.28589134e+01,  1.31161022e+01,
        ...      6.30038828e-02, -3.78738708e+01, -2.49110565e+01,
        ...      3.86065025e+01,  2.52701626e+01, -4.97089103e-02,
        ...     -1.63510494e+01,  1.63965435e+01, -1.22255214e-01,
        ...     -3.07791405e+01,  3.10674877e+01, -4.21732368e+01,
        ...     -1.72333164e+01,  1.67443314e+01, -1.41095228e+01]])
        >>> hkl, scores = pred(theta_chi)
        >>> hkl[:4]
        array([[ -7.,  -3.,   0.],
               [ -5.,   3.,  -5.],
               [ -5.,   3.,  -5.],
               [ -5.,   8.,   0.]])
        >>> np.round(scores[:4], 2)
        ...
        >>>
        """
        sorted_data = theta_chi.transpose()

        # from laue.spot import distance
        # tabledistancerandom = distance(sorted_data, sorted_data, space="cosine")
        import LaueTools.generaltools as GT
        tabledistancerandom = np.transpose(GT.calculdist_from_thetachi(sorted_data, sorted_data))

        codebars_all = []        
        spots_in_center = np.arange(0, len(sorted_data))

        for i in spots_in_center:
            spotangles = tabledistancerandom[i]
            spotangles = np.delete(spotangles, i) # removing the self distance
            # codebars = np.histogram(spotangles, bins=angbins)[0]
            codebars = histogram1d(spotangles, range=[min(self.angbins), max(self.angbins)], bins=len(self.angbins)-1)
            ## normalize the same way as training data
            max_codebars = np.max(codebars)
            codebars = codebars / max_codebars
            codebars_all.append(codebars)
        ## reshape for the model to predict all spots at once
        codebars = np.array(codebars_all)
        ## Do prediction of all spots at once
        prediction = self._predict(codebars)
        max_pred = np.max(prediction, axis=1)
        class_predicted = np.argmax(prediction, axis=1)
        predicted_hkl = self.hkl_data[class_predicted]
        ## return predicted HKL and their softmax confidence
        return predicted_hkl, max_pred

    def generate_orientation(self, s_tth, s_chi, predicted_hkl, spot1_ind, spot2_ind, emax=23):
        """
        Parameters
        ----------
        s_tth : np.ndarray
            The 2*theta vector array.
        s_chi : np.ndarray
            The chi cetor array.
        predicted_hkl : np.array.
            Premiere sortie de self.__call__

        Examples
        --------
        >>> import numpy as np
        >>> from laue.core.hkl_nn.prediction import Predictor
        >>> pred = Predictor("laue/data/Zr02")
        >>>
        >>> params = {'dd': 70.22, 'xcen': 1039.395, 'ycen': 943.57, 'xbet': 0.7478, 'xgam': 0.07186}
        >>> s_tth = 2* np.array(
        ...    [21.407846, 23.937868, 22.2405  , 24.153408, 22.695541, 23.248268,
        ...     24.241102, 24.138845, 24.380188, 23.367207, 23.640224, 23.98681 ,
        ...     23.961515, 23.935892, 27.47521 , 25.00413 , 25.311762, 24.99877 ,
        ...     25.156466, 25.706808, 25.784447, 27.368397, 25.453869, 27.179836,
        ...     26.042637, 26.78874 , 26.50634 , 26.48643 , 27.429255, 27.651321,
        ...     28.350573, 27.772419, 27.223011, 27.333467, 28.183588, 28.566738,
        ...     27.86436 , 30.394827, 29.66095 , 30.336706, 30.444376, 28.307056,
        ...     28.944546, 28.281557, 28.71246 , 29.258598, 31.320158, 29.805788,
        ...     29.776457, 31.620798, 29.531437, 29.629446, 30.925144, 32.030655,
        ...     31.306295, 29.956852, 30.001408, 31.04335 , 32.101448, 30.164719,
        ...     30.134068, 31.973175, 30.434914, 32.085667, 30.54658 , 30.394905,
        ...     32.654804, 30.829573, 31.232382, 31.075354, 31.946472, 31.457209,
        ...     31.991503, 33.70148 , 31.380919, 32.959927, 32.927197, 31.684784,
        ...     32.680996, 31.74713 , 33.357773, 32.748928, 35.733494, 35.01961 ,
        ...     33.76384 , 32.857334, 33.643833, 32.80349 , 33.079655, 32.875328,
        ...     33.81957 , 33.141716, 33.579384, 33.36191 , 33.609825, 33.667408,
        ...     34.253296, 34.124214, 33.668125, 33.81958 , 35.579338, 35.719532,
        ...     34.11531 , 33.968643, 34.5248  , 35.04341 , 34.555008, 34.54157 ,
        ...     34.93492 , 36.44308 , 35.808792, 35.358345, 34.983162, 35.115982,
        ...     35.160065, 37.818913, 35.62279 , 35.162025, 38.085033, 35.07111 ,
        ...     36.04462 , 36.807705, 35.648262, 36.238346, 36.6001  , 36.466553,
        ...     36.160515, 36.66124 , 37.90585 , 36.850773, 36.346252, 36.666294,
        ...     36.98941 , 37.560165, 36.823853, 39.065887, 39.2268  , 37.31787 ,
        ...     37.233906, 37.316513, 37.76289 , 37.790688, 37.4033  , 38.519512,
        ...     38.02746 , 37.79591 , 37.881023, 38.317097, 37.6176  , 39.618195,
        ...     38.21048 , 39.88745 , 38.9187  , 38.418846, 39.894505, 38.64226 ,
        ...     38.673016, 39.13675 , 39.11782 , 39.0221  , 39.03605 , 39.073284,
        ...     38.92352 , 39.079807, 39.354816, 39.271313, 39.34974 , 40.633873,
        ...     40.494247, 39.736656, 39.536896, 40.495255, 40.05513 , 39.82692 ,
        ...     40.41062 , 40.175278, 40.30144 , 40.268475, 40.522114, 40.234386,
        ...     40.583424, 41.503418, 40.255966, 40.493656, 41.334602, 41.728165,
        ...     42.1034  , 41.255764, 41.70883 , 41.53758 , 41.550697, 41.40688 ,
        ...     41.61398 , 41.72424 , 41.775684, 41.76705 , 42.394493, 42.694725,
        ...     42.427128, 42.968616, 42.408966, 42.362007, 43.04908 , 42.359585,
        ...     42.61899 , 42.743206, 42.80929 , 43.42838 , 43.143482, 43.264374,
        ...     43.39156 , 43.591213, 43.488586, 43.576023, 43.83881 , 43.842075,
        ...     44.038486, 44.060547, 44.1449  , 44.11859 , 44.07985 , 44.143806,
        ...     44.31519 , 44.35128 , 44.444744, 44.27597 , 44.632942, 44.607807,
        ...     44.670147, 44.76293 , 44.80089 , 44.835976, 44.966938, 45.126507,
        ...     45.14127 , 45.351093, 45.376312, 45.85324 , 45.877934, 46.00782 ,
        ...     45.843765, 45.992905, 46.37162 , 46.332294, 46.644474, 46.754356,
        ...     46.465168, 46.678898, 46.88352 , 46.47267 , 46.92067 , 46.864185,
        ...     47.173   , 47.32948 , 47.309772, 47.142605, 47.013092, 47.410225,
        ...     47.32998 , 47.27208 , 47.490334, 47.77709 , 47.722866, 48.308605,
        ...     48.397312, 48.254395, 48.383507, 48.769783, 48.41423 , 49.19318 ,
        ...     49.360077, 49.25728 , 48.598232, 49.588367, 49.62911 , 49.025776,
        ...     49.757183, 50.104366, 49.934467, 49.448242, 51.04611 , 50.19547 ,
        ...     50.52417 , 51.835762, 51.573563, 51.07247 , 51.587402, 51.976658,
        ...     51.851284, 52.126583, 52.449825, 52.618923, 51.94187 , 52.747116,
        ...     53.153446, 53.820137, 54.982975, 55.058163, 54.426228, 54.265377,
        ...     53.354504, 54.93776 , 55.376152, 55.752335, 55.408947, 55.98288 ,
        ...     55.683395, 56.396908, 56.75337 , 56.845314, 54.970264, 56.692375,
        ...     55.68737 , 56.48943 , 55.282692, 56.288494, 55.821274, 57.393105,
        ...     56.78071 , 57.84975 , 58.52539 , 55.75702 , 58.172066, 60.318783,
        ...     60.915882, 58.345867, 61.966263, 62.210278, 62.39345 , 62.668297,
        ...     62.63561 , 63.592934, 63.896645, 62.29713 , 64.60493 , 64.69909 ,
        ...     64.78367 , 64.85807 , 64.46475 , 67.316986], dtype=np.float32)
        >>> s_chi = np.array(
        ...   [-8.20532703e+00,  3.21790009e+01, -3.41909170e+00,  2.74034386e+01,
        ...    -4.34071839e-01, -1.56559563e+01,  2.44361897e+01,  2.09223824e+01,
        ...     2.09849014e+01,  4.99572277e+00, -3.35809207e+00,  9.57320690e+00,
        ...     1.19901352e+01, -5.63202202e-01, -3.87633324e+01,  1.70804443e+01,
        ...     1.54516897e+01, -1.07550182e+01,  4.76535940e+00,  1.65281410e+01,
        ...     1.46600618e+01, -2.97682838e+01,  6.23542070e+00, -2.33304462e+01,
        ...     2.29917002e+00, -1.69583626e+01, -7.86655855e+00, -6.16173267e+00,
        ...    -2.00617256e+01, -2.08855991e+01, -2.60995121e+01, -2.03601761e+01,
        ...     9.26190186e+00, -3.26771450e+00, -2.01240082e+01, -2.38944645e+01,
        ...     1.32591028e+01, -3.58275833e+01, -2.97335720e+01,  3.46166496e+01,
        ...    -3.49328651e+01, -1.79303970e+01, -1.40002985e+01,  1.95518032e-01,
        ...     2.18454623e+00, -1.14950457e+01, -3.29807663e+01,  1.88743973e+01,
        ...     1.67924252e+01, -3.26727791e+01, -2.83502388e+00, -6.99001312e+00,
        ...    -2.50557022e+01,  3.50308189e+01, -2.77410622e+01, -5.58232355e+00,
        ...    -5.04871798e+00,  2.30739250e+01,  3.22215805e+01,  9.34048176e+00,
        ...    -3.07650328e+00, -3.04293194e+01,  4.32338238e+00,  3.10291462e+01,
        ...    -2.89001894e+00, -6.45482957e-01, -3.33603897e+01, -8.90020561e+00,
        ...     1.66432037e+01,  1.53302469e+01,  2.57358990e+01,  1.87968693e+01,
        ...     2.28579388e+01,  3.79788818e+01, -6.91721535e+00,  3.05213661e+01,
        ...     3.08364677e+01,  1.49206820e+01, -2.69782314e+01, -3.83367586e+00,
        ...     2.87434654e+01,  1.97967014e+01, -4.60273056e+01, -4.08054428e+01,
        ...     2.94152241e+01,  1.77311916e+01,  2.69437809e+01,  1.02429714e+01,
        ...     1.51231747e+01, -6.40030861e+00, -2.16397858e+01, -9.16009712e+00,
        ...    -1.87940216e+01, -1.31100140e+01,  1.24971237e+01,  9.84316635e+00,
        ...    -1.82992649e+01, -1.53164787e+01, -9.07926655e+00, -5.59934282e+00,
        ...    -3.44886360e+01,  3.42469177e+01, -5.87963057e+00, -4.48785603e-01,
        ...    -1.56945553e+01,  2.21095333e+01, -1.12042456e+01, -4.38081980e+00,
        ...    -1.55494061e+01, -3.58556938e+01, -2.66673031e+01,  1.95756149e+01,
        ...    -1.30536184e+01, -1.18806353e+01, -1.25252562e+01,  4.56511726e+01,
        ...    -2.10193176e+01, -1.01184988e+01,  4.74245529e+01,  7.83739805e-01,
        ...     2.55692654e+01, -3.12942886e+01,  1.40442538e+00,  1.88828678e+01,
        ...    -2.24271317e+01,  1.88044510e+01, -8.43569946e+00,  2.03699665e+01,
        ...     3.55046501e+01, -2.01936340e+01,  2.31074905e+00,  1.26702795e+01,
        ...     1.59207239e+01,  2.72493858e+01, -8.12042522e+00,  4.46173210e+01,
        ...     4.52583237e+01,  1.73486576e+01,  1.41118612e+01,  1.51276274e+01,
        ...    -2.46372719e+01, -2.39885120e+01, -1.42430201e+01,  3.16097260e+01,
        ...    -2.13288364e+01,  1.40513020e+01,  1.28532896e+01, -2.79769096e+01,
        ...     7.04972565e-01, -4.21998940e+01,  1.05170059e+01, -4.20957375e+01,
        ...    -2.49377308e+01,  1.52381029e+01, -4.12661018e+01,  1.35505724e+01,
        ...     1.02339869e+01,  2.76144905e+01, -2.31082268e+01,  1.46324615e+01,
        ...     1.01003742e+01,  4.64928806e-01,  1.28196173e+01,  1.47311342e+00,
        ...    -9.59873295e+00,  2.68206859e+00,  1.03734961e+01,  4.23313904e+01,
        ...    -3.69999199e+01,  2.26480656e+01, -1.90204334e+00,  3.22855721e+01,
        ...     1.72947655e+01, -1.10053968e+01,  2.23560486e+01,  1.63013573e+01,
        ...     1.72622318e+01, -1.10054655e+01,  1.88783150e+01,  8.25482655e+00,
        ...    -1.85908833e+01,  4.21990585e+01, -4.51701552e-01, -4.28545094e+00,
        ...     3.16026268e+01,  3.02397995e+01, -4.08420753e+01, -1.55992270e+01,
        ...     2.62518902e+01,  1.62274055e+01,  1.29832563e+01,  2.43074322e+00,
        ...     1.07625360e+01,  1.74289596e+00,  1.34321604e+01,  2.12204003e+00,
        ...     3.82908287e+01, -4.32963715e+01, -3.13596115e+01, -4.31565247e+01,
        ...    -2.96992035e+01,  1.04633722e+01, -3.83834953e+01,  1.31570702e+01,
        ...    -6.78970861e+00,  1.05209122e+01,  1.85651016e+01,  4.29506416e+01,
        ...     3.68172336e+00,  1.05411434e+00,  7.80042028e+00, -2.22817516e+01,
        ...    -3.28606105e+00,  1.57109947e+01, -3.67313313e+00,  2.49480610e+01,
        ...    -3.28707695e+00, -1.95406990e+01, -3.95066929e+00, -1.27304811e+01,
        ...    -2.03769913e+01, -9.41535378e+00, -3.08649349e+01,  2.76702118e+01,
        ...    -3.70032239e+00, -8.94166470e-01, -3.58918037e+01, -1.01778631e+01,
        ...     2.02616730e+01,  2.79342270e+01, -3.34449043e+01,  4.04138489e+01,
        ...     2.50965834e+00, -3.38570976e+01,  2.75537510e+01, -3.37098198e+01,
        ...     1.44837494e+01,  7.50045109e+00,  1.40488930e+01, -1.02703829e+01,
        ...    -1.07151127e+00, -1.31155243e+01,  2.43269215e+01,  2.47291718e+01,
        ...    -3.47581053e+00, -4.43205953e-01, -3.64747047e+01, -2.42184029e+01,
        ...    -1.52997613e+00,  3.71201897e+01,  1.29990506e+00, -2.58895760e+01,
        ...    -1.69234409e+01, -6.38067770e+00,  9.71880555e-01,  2.28067226e+01,
        ...    -3.57630348e+01, -1.48928843e+01,  2.56321697e+01, -3.56116333e+01,
        ...    -3.36559181e+01, -3.16772633e+01, -3.89247475e+01, -1.83768864e+01,
        ...     1.58960209e+01, -3.29572601e+01, -2.96418972e+01,  1.31469431e+01,
        ...     3.26644249e+01, -1.11847486e+01,  6.91002798e+00, -1.87717667e+01,
        ...     3.64399223e+01, -4.51707697e+00, -4.32118148e-01,  3.18794842e+01,
        ...     1.44058733e+01,  1.37111673e+01, -2.27398357e+01, -4.26825180e+01,
        ...    -2.83456326e+00,  3.29872704e+01,  2.67745304e+01, -1.32994819e+00,
        ...    -1.54123325e+01, -2.65425949e+01,  1.39097233e+01,  8.81372738e+00,
        ...     1.20746326e+01,  2.88423542e-02,  1.39288521e+01,  1.24434137e+01,
        ...     2.86415615e+01, -1.42222195e+01, -3.12223792e+00,  2.29418468e+01,
        ...    -5.42705345e+00, -8.21866131e+00, -2.16707993e+01,  2.54728794e+01,
        ...    -3.65554237e+01, -1.73211784e+01, -2.03518295e+00, -1.03724775e+01,
        ...    -1.85134792e+01, -6.88719845e+00,  1.53673096e+01, -1.19471617e+01,
        ...    -1.41730249e+00, -7.46977520e+00, -3.57569771e+01,  1.43709793e+01,
        ...    -2.99577198e+01, -1.80457935e+01,  3.37878799e+01,  2.52171669e+01,
        ...    -3.16626091e+01,  1.34134636e+01, -2.73285046e+01, -1.53215799e+01,
        ...     1.20265036e+01,  4.32097359e+01,  2.73963318e+01, -4.08462715e+00,
        ...    -3.03847313e+00,  3.98676071e+01,  1.47413588e+01,  1.52423782e+01,
        ...     1.27146530e+01,  1.12880945e+01,  1.22942419e+01,  5.47081375e+00,
        ...     3.27725101e+00,  2.99607716e+01, -4.89247322e+00, -6.39366055e+00,
        ...    -8.49700642e+00, -1.18187237e+01, -2.43182430e+01,  1.39376507e+01], dtype=np.float32)
        >>> predicted_hkl = np.array(
        ...    [[-8, 2, 7], [0, -5, -4], [-1, 8, 6], [4, -1, -2], [-4, 5, 3], [6, -3, -7], [-2, 4, -5], [-3, -4, 1],
        ...     [9, 3, -1], [-6, -8, 3], [-3, -2, -4], [2, 7, 3], [9, 4, -8], [1, -1, 8], [6, -1, -3], [-6, -1, -5],
        ...     [-2, -9, 8], [-8, -5, 2], [10, -1, -5], [2, 11, 0], [-2, -1, -11], [2, 10, -5], [3, -3, -2], [-6, 5, 3],
        ...     [5, -3, 1], [-3, 8, -5], [-6, -1, 1], [-2, 6, -5], [0, -6, 5], [-8, 1, -7], [9, 4, -8], [-4, -7, 0],
        ...     [-10, -5, 7], [9, 4, 4], [-4, -5, 0], [6, -4, -7], [-6, 8, 13], [0, -6, 5], [1, 4, -8], [-4, 6, -5],
        ...     [9, -1, 3], [5, 10, -1], [2, -11, -5], [1, 12, 4], [5, -3, -9], [8, -4, -3], [-6, -3, 5], [-10, -3, 4],
        ...     [2, 6, -3], [3, 7, -9], [-4, 11, -3], [2, 7, -8], [6, 9, -2], [8, 5, 4], [-8, 0, -6], [2, 1, -9],
        ...     [-6, -5, 7], [-5, -11, -5], [0, -11, 3], [-2, -2, -1], [-7, 13, -3], [-1, -10, 8], [3, -5, -5], [-6, -11, 6],
        ...     [-10, -7, -4], [-10, 1, -5], [4, -5, 1], [8, -1, -2], [1, 4, -9], [-8, 9, 0], [-5, -6, -4], [4, -10, 1],
        ...     [-5, 2, 11], [5, -8, -3], [-10, 2, -7], [0, 7, 11], [4, -4, -7], [-4, 11, 6], [-2, 7, 2], [5, 2, -7],
        ...     [5, 7, -5], [-4, -3, 5], [4, -3, 2], [-4, 8, -5], [8, 3, -6], [-3, 7, -9], [-5, -8, -6], [3, 1, 0],
        ...     [9, -3, -8], [1, -2, 7], [10, 5, -3], [-1, -6, 5], [-3, 11, 6], [-7, -13, -4], [-8, 2, -9], [8, -3, 3],
        ...     [7, -2, -9], [12, 5, -6], [-9, 13, -3], [-5, 1, -8], [11, 3, -4], [1, -7, 2], [5, -3, -9], [-11, 6, 2],
        ...     [-6, 3, 11], [1, 6, -12], [4, 2, -3], [-13, -2, -2], [5, 10, 7], [-6, 2, -3], [-12, 2, 7], [-9, 1, -9],
        ...     [4, 6, -5], [-1, 2, -8], [9, -4, -5], [1, -11, -3], [3, 1, -4], [1, 3, -6], [-6, -1, 6], [-7, 1, 9],
        ...     [7, -3, 3], [1, 5, -2], [-7, -9, -1], [0, -11, -7], [7, -2, -12], [5, -1, -8], [-1, -8, -9], [-4, 5, 11],
        ...     [-1, 6, -7], [1, 4, -2], [-10, -9, 1], [-2, -1, 0], [-2, 1, -1], [-1, 6, 13], [-3, 2, -14], [5, 5, -9],
        ...     [-2, 3, 7], [-8, 5, 1], [-1, 10, 0], [8, 1, -6], [5, -5, -11], [-1, -2, 10], [5, -2, -10], [-2, -9, 6],
        ...     [-2, -3, 6], [-7, -2, 5], [3, 2, -14], [-1, 1, 1], [-1, -2, -12], [-1, 2, 0], [-13, -3, -3], [1, -3, 3],
        ...     [3, 3, 1], [-7, -1, -6], [-5, -11, 3], [-6, 1, 13], [-1, -7, 7], [-9, -5, 9], [7, 9, -7], [1, -3, -10],
        ...     [9, -8, -7], [-4, -5, 10], [-7, 1, 9], [5, 1, 9], [-6, 5, 3], [-6, 12, -1], [1, 7, 0], [2, 4, 1],
        ...     [1, -4, -5], [3, 3, 10], [0, 3, -2], [4, 3, -3], [-2, 1, -13], [-7, -7, 12], [9, 2, -8], [5, -13, 8],
        ...     [6, 3, 11], [3, -5, -5], [9, 3, 2], [4, 11, -2], [-3, 1, -1], [-5, -2, -8], [5, -1, 1], [-3, 9, -7],
        ...     [-5, 3, -6], [-1, 3, -6], [4, -8, 1], [8, 4, -1], [4, 2, -3], [-2, -2, 13], [-9, -2, 10], [5, -5, -11],
        ...     [-4, -5, -6], [9, 5, 1], [3, 2, -14], [11, -10, -3], [7, 3, 1], [-8, 1, 3], [0, -11, -4], [-4, 2, -3],
        ...     [-9, -1, 8], [2, -9, -4], [-3, 6, -1], [5, 6, -2], [11, 3, -9], [-1, 14, 4], [3, -2, 6], [-5, 10, 4],
        ...     [2, -11, -6], [1, 14, -2], [3, -2, 10], [3, -4, 5], [10, 3, -13], [-2, -6, 11], [-3, 3, 10], [-3, -7, 8],
        ...     [-5, 10, 6], [-2, -5, 2], [5, -5, -11], [2, -11, -8], [5, -8, -5], [-10, 1, 12], [6, -5, -9], [-8, -3, 3],
        ...     [1, -9, 9], [9, 4, 1], [-6, 8, 1], [7, 3, 7], [-4, -12, 3], [-7, -9, -1], [-2, 13, -3], [9, 3, -1],
        ...     [-4, -5, -7], [0, 7, 11], [-6, 11, -5], [2, 1, 8], [-7, 1, -1], [-2, -2, 9], [0, -5, -9], [13, -6, 1],
        ...     [8, -2, -11], [-8, 3, -9], [5, 6, 0], [-2, 2, 7], [11, -1, -8], [2, 6, -3], [1, -7, 11], [6, 9, 4],
        ...     [1, 1, 10], [5, 7, 1], [-1, -3, 13], [9, 0, 4], [-6, -10, -1], [4, -4, 11], [-5, -1, 0], [-1, -2, -3],
        ...     [3, 6, 4], [7, -2, -12], [5, -3, 7], [10, 11, -3], [2, 5, 11], [-1, -8, -12], [-4, 3, 8], [5, -7, -9],
        ...     [-7, -2, 10], [6, 1, 1], [6, 1, 11], [2, 4, -7], [-6, -6, 5], [-13, 2, 9], [-7, -2, 8], [1, -1, 5],
        ...     [1, -5, 10], [-1, -7, 7], [7, -9, -3], [-2, 7, 2], [3, -5, 0], [3, -5, 0], [11, 5, -7], [7, 0, 2],
        ...     [6, -1, -9], [-7, -3, -6], [-12, 6, 1], [11, -8, -3], [-4, -7, -4], [-7, -3, 0], [3, -4, -14], [-2, 5, -10],
        ...     [0, -1, 3], [-7, -7, -3], [2, -5, 8], [2, -5, 0], [12, -1, 2], [7, 1, -3], [-11, -3, -2], [1, -1, -4],
        ...     [-3, 5, -6], [9, -5, -12], [11, -1, -8], [-3, 6, -1], [-2, 5, -4], [-1, -7, 2], [10, -4, -5], [5, 6, -2],
        ...     [2, 3, -3], [-1, 1, 11], [1, -6, -3], [7, 3, -2], [1, -5, 6], [-7, 7, 6], [1, -7, 3], [0, -7, -5],
        ...     [-8, -8, -3], [-4, -3, 9], [1, -12, -5], [1, 7, -3], [6, 4, -5], [1, -2, -12], [7, -2, -6], [1, -7, 2],
        ...     [2, 7, -8], [4, -3, 0], [3, 3, 5], [-4, -3, 1], [4, -3, 6], [5, 4, 4], [5, 10, -2], [-7, -2, 0],
        ...     [6, -5, 0], [-1, 9, -4], [0, -7, -5], [-3, -4, 9], [-5, -6, 7], [2, -1, -5], [0, 2, 7], [-7, 7, 1],
        ...     [-6, -1, 6], [6, 5, -5], [6, -1, -5], [-3, 2, -1]])
        >>> spot1_ind, spot2_ind
        >>> pred.generate_orientation(s_tth, s_chi, predicted_hkl, spot1_ind, spot2_ind)
        >>>
        """
        # spots_in_center = np.arange(0, len(s_tth))
        import LaueTools.generaltools as GT
        import LaueTools.CrystalParameters as CP
        import LaueTools.findorient as FindO
        from LaueTools.matchingrate import Angular_residues_np
        import LaueTools.dict_LaueTools as dictLT

        dist = GT.calculdist_from_thetachi(np.array([s_tth/2., s_chi]).T,
                np.array([s_tth/2., s_chi]).T)

        dist_ = dist[spot1_ind, spot2_ind]

        lattice_params = dictLT.dict_Materials[self.material][1]
        B = CP.calc_B_RR(lattice_params)

        Gstar_metric = CP.Gstar_from_directlatticeparams(lattice_params[0],lattice_params[1],\
                                                         lattice_params[2],lattice_params[3],\
                                                         lattice_params[4],lattice_params[5])

        ## list of equivalent HKL
        hkl1_list = self.hkl_all_class[str(predicted_hkl[spot1_ind])] # TODO: tuple plutot que str.
        hkl2_list = self.hkl_all_class[str(predicted_hkl[spot2_ind])] # TODO: tuple plutot que str.
        tth_chi_spot1 = np.array([s_tth[spot1_ind], s_chi[spot1_ind]])
        tth_chi_spot2 = np.array([s_tth[spot2_ind], s_chi[spot2_ind]])
        ## generate LUT to remove possibilities of HKL
        hkl_all = np.vstack((hkl1_list, hkl2_list))
        LUT = FindO.GenerateLookUpTable(hkl_all, Gstar_metric)
        hkls = FindO.PlanePairs_2(dist_, 0.5, LUT, onlyclosest=1)

        if np.all(hkls == None):
            print("Nothing found")
            return np.zeros((3,3)), 0.0

        rot_mat = []
        mr = []
        for ii in range(len(hkls)):
        # ii = 0
            rot_mat1 = FindO.OrientMatrix_from_2hkl(hkls[ii][0], tth_chi_spot1, \
                                                    hkls[ii][1], tth_chi_spot2,
                                                    B)

            AngRes = Angular_residues_np(rot_mat1, s_tth, s_chi,
                                                key_material=self.material,
                                                emax=emax,
                                                ResolutionAngstrom=False,
                                                ang_tol=0.5,
                                                detectorparameters=self.dict_dp,
                                                dictmaterials=dictLT.dict_Materials)
            allres, _, nbclose, nballres, _, _ = AngRes
            match_rate = nbclose/nballres
            rot_mat.append(rot_mat1)
            mr.append(match_rate)

        max_ind = np.argmax(mr)

        return rot_mat[max_ind], mr[max_ind]