#!/usr/bin/env python3

"""
** Permet de manipuler un diagramme de Laue unique. **
-----------------------------------------------------

Notes
-----
Si le module ``psutil`` est installe, la memoire sera mieux geree.
"""

import hashlib
import math
import numbers
import os

import cv2
import numpy as np
try:
    import psutil # Pour acceder a la memoire disponible.
except ImportError:
    psutil = None

from laue.spot import Spot
from laue.core.subsets import Splitable
from laue.utilities.serialization import DiagramPickleable

__pdoc__ = {"LaueDiagram.__contains__": True,
            "LaueDiagram.__getitem__": True,
            "LaueDiagram.__hash__": True,
            "LaueDiagram.__iter__": True,
            "LaueDiagram.__len__": True}


class LaueDiagram(Splitable, DiagramPickleable):
    """
    Represente un diagramme de Laue associe a une seule image.
    """
    def __init__(self, name, experiment):
        """
        Notes
        -----
        * L'utilisateur n'a pas a generer des objets issus de cette classe.
        Ils sont generes automatiquement par des instances de ``laue.experiment.base_experiment.Experiment``.
        * Il n'y a pas de verifications faites sur les entrees car l'utilisateur
        ne doit pas toucher a l'initialisateur. La performance passe donc avant
        l'enorme mefiance envers les humains.

        Parameters
        ----------
        name : str
            Nom de l'image du diagramme.
        experiment : Experiment
            Instance de l'experience qui contient ce diagramme.
            Cet objet doit heriter de ``laue.experiment.base_experiment.Experiment``.
        """
        self._name = name
        self.experiment = experiment # C'est l'experience qui contient ce diagramme.
        self._spots = [] # La liste des spots en vrac. Ils doivent etres remplis par ailleur.

        # Declaration des variables futur.
        self._quality = None # Facteur qui dit a quel point ce diagramme est joli a l'oeil.
        self._image_xy = None # L'image brute avec le fond et tout.
        self._image_gnom = None # Image projete dans le plan gnomonic.
        self._sorted_spots = {} # Les listes des spots tries selon un ordre particulier.
        self._axes = {} # Les axes de zones.
        self._subsets = {} # Les sous ensembles.
        self._spots_set = None # L'ensemble des spots pour une recherche plus rapide.
        self._hkl = {} # Les prediction des indices hkl

    def _set_spots(self, spots):
        """
        ** Met les spots dans le diagrame. **

        Parameters
        ----------
        spots : list
            Ensemble des points chauds. Ils doivent heriter de ``laue.spot.Spot``.
            Pas set car l'ordre doit etre fige.
        """
        self._spots = spots

    def _set_image(self, image):
        """
        ** Ajoute le contenu de l'image brute. **

        Parameters
        ----------
        image : np.ndarray
            L'image 2d en niveau de gris encodee en np.uint16.
        """
        self._image_xy = image

    def find_zone_axes(self, *, dmax=None, nbr=7, tol=None,
        _axes_args=None, _get_args=False, **_):
        """
        ** Cherche les axes de zone **

        Notes
        -----
        Si le but est d'extraire les axes de zonnes de plusieurs diagrammes
        il vaut mieux appeler ``laue.experiment.base_experiment.Experiment.find_zone_axes`` car
        les calculs sont parallelises, contrairement a cette methode.

        Parameters
        ----------
        dmax : float, optional
            La distance maximale admissible entre un spot et un axe de zone
            pour pouvoir considerer que le spot appartient a l'axe de zone.
            Par defaut cette valeur evolue lineairement entre 5 pxl pour
            les diagrammes contenants beaucoup de spots a 20 pxl pour les petits.
            avec ``n`` le nombre de spots dans le diagramme.
        tol : float, optional
            Alignement des points. Voir ``laue.core.geometry.transformer.Transformer.hough_reduce``
            pour avoir les informations precises sur 'tol'. Par defaut
            cette valeur evolue exponentiellement entre 0.018 pour les diagrammes
            de 50 spots et 0.005 pour ceux de 600 spots.
        nbr : int, optional
            Nombre minimum de points par axe de zone.

        Returns
        -------
        axis : list
            La liste des axes de zone de type ``laue.zone_axis.ZoneAxis``.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image, config_file="laue/examples/ge_blanc.det")[0]
        >>> type(diag.find_zone_axes())
        <class 'list'>
        >>> type(diag.find_zone_axes().pop())
        <class 'laue.zone_axis.ZoneAxis'>
        >>>
        """
        if dmax is None:
            pxl_max, pxl_min = 20, 5
            d_max, d_min = 1.2*pxl_max/2048, 1.2*pxl_min/2048
            dmax = max(.005, d_max - (d_max-d_min)/800 * len(self))
        if tol is None:
            a = 2.2865e-8
            b = -3.9201e-5
            c = .0205058
            tol = a*len(self)**2 + b*len(self) + c

        assert isinstance(dmax, float), \
            f"'dmax' doit etre un flottant, pas un {type(dmax).__name__}."
        assert dmax > 0, f"La distance doit etre strictement positive elle vaut {dmax}."

        if _get_args: # Si il faut seulement preparer le travail.
            if (dmax, nbr, tol) in self._axes:
                return None, None, dmax, nbr, tol # Pour accelerer les calculs.
            gnomonics = self.get_gnomonic_positions()
            return self.experiment.transformer, gnomonics, dmax, nbr, tol

        if (dmax, nbr, tol) in self._axes: # Si on a deja la solution.
            return self._axes[(dmax, nbr, tol)]

        if _axes_args is None: # Si le travail n'est pas premache.
            if self.experiment.verbose:
                print(f"Recherche des axes de {self.get_id()}...")
            from laue.core.zone_axes import atomic_find_zone_axes
            phi_s, mu_s, axis_spots_ind, spots_axes_ind = atomic_find_zone_axes(
                *self.find_zone_axes(dmax=dmax, nbr=nbr, tol=tol, _get_args=True))
            if self.experiment.verbose:
                print(f"    OK: {len(axis_spots_ind)} axes trouves.")
        else:
            phi_s, mu_s, axis_spots_ind, spots_axes_ind = _axes_args

        # Creation des objets 'ZoneAxis'.
        from laue.zone_axis import ZoneAxis
        self._axes[(dmax, nbr, tol)] = [
            ZoneAxis(diagram=self,
                     spots_ind=spots_ind,
                     identifier=i,
                     phi=phi,
                     mu=mu)
            for i, (phi, mu, spots_ind) in enumerate(zip(phi_s, mu_s, axis_spots_ind))]

        return self._axes[(dmax, nbr, tol)]

    def get_gnomonic_positions(self, *, n=None, sort=None):
        """
        ** Recupere la position des spots dans le plan gnomonic. **

        Parameters
        ----------
        n : int, optional
            Same as ``LaueDiagram.select_spots``.
        sort : str or callable, optional
            Same as ``LaueDiagram.select_spots``.

        Returns
        -------
        coordonees : np.ndarray
            * Le vecteur des coordonnees x puis le vecteur y. (en mm)
            * La shape de retour est (2, nbr_spots)

        Raises
        ------
        AttributError
            Si il manque des infos pour satisfaire cette demande.
            En general l'un des parametres de set_calibration.

        Examples
        --------
        >>> import numpy as np
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image, config_file="laue/examples/ge_blanc.det")[0]
        >>> diag.get_gnomonic_positions().shape
        (2, 78)
        >>> np.round(diag.get_gnomonic_positions(n=4, sort="quality"), 2)
        array([[ 0.25,  0.08,  0.27, -0.26],
               [ 0.32,  0.01, -0.3 , -0.2 ]], dtype=float32)
        >>>
        """
        # On calcul les projections pour tous les points a la fois.
        if self._spots[0]._gnomonic is None:
            coords_gnomonic = self.experiment.transformer.cam_to_gnomonic(
                *self.get_positions(n=n, sort=sort),
                self.experiment.set_calibration())
            for spot, xg, yg in zip(self, *coords_gnomonic):
                spot._gnomonic = (xg, yg)
        # On extrait juste ce qu'il nous interresse.
        else:
            coords_gnomonic = np.array(
                [spot.get_gnomonic() for spot in self.select_spots(n=n, sort=sort)],
                ).transpose()

        return coords_gnomonic

    def get_id(self):
        """
        ** Retourne le nom du diagramme. **

        * Dans la mesure du possible, le nom du diagramme est le chemin
        d'acces au fichier image qui a permis de constituer le diagramme.
        * Si le chemin d'acces est inconnu, un nom par defaut unique est genere.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image)[0]
        >>> diag.get_id()
        'laue/examples/ge_blanc.mccd'
        >>>
        """
        return self._name

    def get_image_gnomonic(self):
        """
        ** Recupere le contenu de l'image d'un diagramme projete dans le plan gnomonic. **

        Notes
        -----
        Les parametres de set_calibration de la camera sont recuperes avec
        un appel a la fonction ``laue.experiment.base_experiment.Experiment.set_calibration()``.

        Returns
        -------
        image: np.ndarray(dtype=np.uint16)
            L'image 2d en niveau de gris encodee en uint16.
        
        Raises
        ------
        NameError
            Si l'image est introuvable.
        AttributError
            Si il manque des infos pour satisfaire cette demande.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image, config_file="laue/examples/ge_blanc.det")[0]
        >>> diag.get_image_gnomonic()
        array([[0, 0, 0, ..., 0, 0, 0],
               [0, 0, 0, ..., 0, 0, 0],
               [0, 0, 0, ..., 0, 0, 0],
               ...,
               [0, 0, 0, ..., 0, 0, 0],
               [0, 0, 0, ..., 0, 0, 0],
               [0, 0, 0, ..., 0, 0, 0]], dtype=uint16)
        >>>
        """
        if self._image_gnom is not None:
            return self._image_gnom

        if self.experiment.verbose:
            print(f"Image gnomonic de {self.get_id()}...")

        # Interpolation inverse vers l'image finale.
        map_x, map_y, _ = self.experiment._get_gnomonic_matrix()
        image_xy = self.get_image_xy()
        image_gnom = cv2.remap(image_xy,
            map_x, map_y, interpolation=cv2.INTER_LINEAR)

        if psutil is not None and psutil.virtual_memory().percent < 75:
            self._image_gnom = image_gnom

        if self.experiment.verbose:
            print(f"    OK: Image gnomonic caluculee.")

        return image_gnom

    def get_image_xy(self):
        """
        ** Recupere le contenu de l'image d'un diagramme. **

        Returns
        -------
        image : np.ndarray(dtype=np.uint16)
            L'image 2d en niveau de gris encodee en uint16.
        
        Raises
        ------
        NameError
            Si l'image est introuvable.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image)[0]
        >>> diag.get_image_xy()
        array([[0, 0, 0, ..., 0, 0, 0],
               [0, 0, 0, ..., 0, 0, 0],
               [0, 0, 0, ..., 0, 0, 0],
               ...,
               [0, 0, 0, ..., 0, 0, 0],
               [0, 0, 0, ..., 0, 0, 0],
               [0, 0, 0, ..., 0, 0, 0]], dtype=uint16)
        >>> diag.get_image_xy().max()
        28899
        >>>
        """
        if self._image_xy is not None:
            return self._image_xy

        if not os.path.exists(self.get_id()):
            raise NameError(f"Impossible de trouver le fichier {repr(self.get_id())}.")

        from laue.utilities.image import read_image
        image = read_image(self.get_id())

        if psutil is not None and psutil.virtual_memory().percent < 75:
            self._image_xy = image

        return image

    def get_neighbors(self, spot, *, space=None, n_max=None, d_max=None):
        """
        ** Recupere des spots proches. **

        Parameters
        ----------
        spot : int, laue.spot.Spot, tuple
            - Le spot a considerer, celui de reference.
                - int => Considere le item(ieme) spot. Comme si un
                    ``LaueDiagram`` etait une liste de ``laue.spot.Spot``.
                - ``laue.spot.Spot`` => Prend directement le
                    spot fourni come spot de reference.
                - tuple => Les 2 coordonnees qui caracterisent le spot.
                    Il peuvent etre exprime dans 3 reperes differents.
                    Celui de la camera, celui dans le plan gnomonic, et celui angulaire en theta chi.
                    - (int, int) => Interprete comme x_camera et y_camera en pxl.
                    - (float, float) => Interprete comme x_gnomonic et y_gnomonic en mm.
        space : str
            Given to ``laue.spot.distance``.
        n_max : int
            C'est le nombre maximum de voisins (reference comprise) a renvoyer.
            C'est la taille maximal de la liste renvoyee. Par defaut, il n'y a pas de limite.
        d_max : number
            C'est la distance maximal qui peut separer le spot de reference
            aux autres spots. Par defaut, ce rayon est infini.

        Returns
        -------
        list
            La liste contenant les spots de type ``laue.spot.Spot``.
            Les spots sont ordonnes du plus proche au plus lointain.
            Le premier element peut etre le spot de reference si il existe.

        Raises
        ------
        ValueError
            Si l'une des valeur fournie n'est pas coherente.
        TypeError
            Si l'un des type est absurde.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image)[0]
        >>> spot, = diag.select_spots(n=1, sort="intensity")
        >>> spot
        Spot(position=(622.09, 1656.72), quality=0.949)
        >>>
        >>> type(diag.get_neighbors(0))
        <class 'list'>
        >>> len(diag.get_neighbors(0)) == len(diag)
        True
        >>> len(diag.get_neighbors(0, n_max=2))
        2
        >>>
        >>> diag.get_neighbors((622, 1657), n_max=2)
        [Spot(position=(622.09, 1656.72), quality=0.949), Spot(position=(562.63, 1802.56), quality=0.603)]
        >>> diag.get_neighbors((622, 1657), d_max=10.0)
        [Spot(position=(622.09, 1656.72), quality=0.949)]
        >>>
        >>> diag.get_neighbors(spot, n_max=2)
        [Spot(position=(622.09, 1656.72), quality=0.949), Spot(position=(562.63, 1802.56), quality=0.603)]
        >>>
        """
        # Extraction des position du spot.
        if isinstance(spot, (int, np.integer)): # Si le spot est designe par son rang.
            spot = self[spot] # On recupere l'instance du spot lui-meme.
        if isinstance(spot, Spot): # Si le spot est trop complexe.
            if space is None or space == "camera":
                spot = spot.get_position()
            elif space == "gnomonic":
                spot = spot.get_gnomonic()
            elif space == "angle":
                spot = spot.get_theta_chi()
            else:
                raise ValueError(f"L'espace {space} est pas connu. "
                    "Seul, 'camera', 'gnomonic' et 'angle' sont admissibles.")
        elif isinstance(spot, tuple):
            if len(spot) != 2:
                raise ValueError("Si le spot de reference est un tuple, il doit "
                    f"contenir exactement 2 elements, pas {len(spot)}.")
            if type(spot[0]) != type(spot[1]):
                raise TypeError("Les 2 coordonnees doivent etre homogenes")

            # Recherche de la metrique
            if not isinstance(spot[0], (int, np.integer, float)):
                raise TypeError("Les 2 coordonnes doivent etre de type int ou float, "
                    f"pas de type {type(spot[0]).__name__}.")
            if space is None:
                space = "camera" if isinstance(spot[0], (int, np.integer)) else "gnomonic"

        else:
            raise TypeError("Seul les types 'int', 'tuple' et 'Spot' sont supportees. "
                f"Or le type fourni est {type(spot).__name__}.")
        
        if self.experiment.verbose:
            print(f"Recherche des voisins du spot {spot}...")

        if space is None:
            space = "camera"

        # Recherche des voisins
        from laue.spot import distance

        d_list = distance(spot, self.select_spots(), space=space)
        nbr = len(self)
        if d_max is not None:
            if not isinstance(d_max, numbers.Number):
                raise TypeError(f"'d_max' has to be a number, not a {type(d_max).__name__}.")
            if d_max <= 0:
                raise ValueError(f"'d_max' doit etre strictement positif. Or il vaut {d_max}.")
            nbr = (d_list <= d_max).sum()
        if n_max is not None:
            if not isinstance(n_max, int):
                raise TypeError(f"'n_max' has to be a integer, not a {type(n_max).__name__}.")
            if n_max < 1:
                raise ValueError(f"Il faut selectioner au moin 1 voisin. {n_max} c'est pas suffisant.")
            nbr = min(nbr, n_max)

        neighbors = [self._spots[spot_ind] for spot_ind in np.argsort(d_list)[:nbr]]
        if self.experiment.verbose:
            print(f"    OK: il y a {len(neighbors)} voisins.")
        return neighbors

    def get_positions(self, *, n=None, sort=None, **kwds):
        """
        ** Recupere la position des spots dans le plan de la camera. **

        Parameters
        ----------
        n : int, optional
            Same as ``LaueDiagram.select_spots``.
        sort : str or callable, optional
            Same as ``LaueDiagram.select_spots``.
        **kwds
            Les parametres de ``laue.spot.Spot.get_position``.

        Returns
        -------
        np.ndarray
            * Le vecteur des coordonnees x puis le vecteur des y. (en pxl)
            * La shape de retour est (2, nbr_spots).

        Examples
        --------
        >>> import numpy as np
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image)[0]
        >>> diag.get_positions().shape
        (2, 78)
        >>> np.round(diag.get_positions(n=4, sort="quality"))
        array([[ 622.,  932., 1243., 1276.],
               [1657., 1214., 1661.,  599.]])
        >>>
        """
        return np.array(
            [spot.get_position(**kwds) for spot in self.select_spots(n=n, sort=sort)],
            ).transpose()

    def get_quality(self):
        r"""
        ** Estime a quel point le diagramme est joli. **

        Returns
        -------
        quality : float
            * Un scalaire qui permet de juger de la purete du diagramme:
            * 0.0 => diagramme tres moche, illisible a l'oeil.
            * 0.2 => diagramme pas bien joli.
            * 0.8 => diagramme bien joli, avec de belles taches.
            * 1.0 => diagramme super joli, bien epure avec des taches rondes et intenses.

        Examples
        --------
        >>> import laue
        >>> images = ("laue/examples/ge_blanc.mccd", "laue/examples/roi1_0001.mccd")
        >>> diag1, diag2 = laue.experiment.base_experiment.Experiment(images)[:2]
        >>>
        >>> print(f"quality: {diag1.get_quality():.4f}")
        quality: 0.8344
        >>> print(f"quality: {diag2.get_quality():.4f}")
        quality: 0.5153
        >>>
        """
        def f_nbr(x, n_best_min, n_best_max):
            """
            f(x=0) = 0
            f(x=n_best_min) = 1
            f(x=n_best_max) = 1
            f(x=2*n_best_max) = 1/2
            f(x=oo) = 0
            """
            if x < n_best_min:
                return x / n_best_min
            if n_best_min <= x < n_best_max:
                return 1
            return math.exp(-(x-n_best_max)*(math.log(2)/n_best_max))

        if self._quality is not None:
            return self._quality

        spot_qual_weight = 0.5

        self._quality = (1-spot_qual_weight)*f_nbr(len(self), 60, 120) + spot_qual_weight*np.mean([spot.get_quality() for spot in self])
        return self._quality

    def get_theta_chi(self, *, n=None, sort=None):
        """
        ** Recupere la representation angulaire des spots. **

        Parameters
        ----------
        n : int, optional
            Same as ``LaueDiagram.select_spots``.
        sort : str or callable, optional
            Same as ``LaueDiagram.select_spots``.

        Returns
        -------
        np.ndarray
            * Le vecteur des angles theta puis chi. (en deg)
            * La shape de retour est (2, nbr_spots).

        Examples
        --------
        >>> import numpy as np
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image, config_file="laue/examples/ge_blanc.det")[0]
        >>> diag.get_theta_chi().shape
        (2, 78)
        >>> np.round(diag.get_theta_chi(n=4, sort="quality"))
        array([[ 29.,  40.,  29.,  58.],
               [ 20.,   1., -18., -21.]], dtype=float32)
        >>>
        """
        # On calcul les projections pour tous les points a la fois.
        if self._spots[0]._thetachi is None:
            angles_thetachi = self.experiment.transformer.cam_to_thetachi(
                *self.get_positions(n=n, sort=sort),
                self.experiment.set_calibration())
            for spot, theta, chi in zip(self, *angles_thetachi):
                spot._thetachi = (theta, chi)
        # On extrait juste ce qu'il nous interresse.
        else:
            angles_thetachi = np.array(
                [spot.get_theta_chi() for spot in self.select_spots(n=n, sort=sort)],
                ).transpose()

        return angles_thetachi

    def plot_all(self, *, display=True):
        """
        ** Affiche le diagramme a l'ecran. **

        * Utilise le module ``matplotlib`` qui doit etre installe.
        * Cette methode peut prendre du temps car elle affiche le maximum de choses possible.

        Parameters
        ----------
        display : boolean
            Si True, affiche a l'ecran en faisant appel a ``plt.show()``.

        Returns
        -------
        matplotlib.figure.Figure
            La figure matplotlib completee.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image, config_file="laue/examples/ge_blanc.det")[0]
        >>> diag.plot_all(display=False)
        <Figure size 640x480 with 2 Axes>
        >>>
        """
        import matplotlib.pyplot as plt

        fig = plt.figure()
        fig.suptitle(self.get_id())
        axe_xy = fig.add_subplot(1, 2, 1)
        axe_gnomonic = fig.add_subplot(1, 2, 2)

        self.plot_xy(axe_xy, display=False)

        try:
            self.plot_gnomonic(axe_gnomonic, display=False)
        except AttributeError:
            pass

        if display:
            plt.show()

        return fig

    def plot_gnomonic(self, axe_pyplot=None, *, display=True):
        """
        ** Prepare l'affichage du diagramme dans le plan gnomonic. **

        Parameters
        ----------
        axe_pyplot : Axe
            Axe matplotlib qui supporte les methodes ``.scatter`` et ``.imshow``.
        display : boolean
            Si True, affiche a l'ecran en faisant appel a ``plt.show()``.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image, config_file="laue/examples/ge_blanc.det")[0]
        >>>

        Sans preciser l'axe.
        >>> diag.plot_gnomonic(display=False)
        <AxesSubplot:title={'center':'plan gnomonic'}, xlabel='x.Gi (mm)', ylabel='y.Gj (mm)'>
        >>>

        En precisant l'axe.
        >>> import matplotlib.pyplot as plt
        >>> fig = plt.figure()
        >>> axe = fig.add_subplot()
        >>> diag.plot_gnomonic(axe, display=False)
        <AxesSubplot:title={'center':'plan gnomonic'}, xlabel='x.Gi (mm)', ylabel='y.Gj (mm)'>
        >>>
        """
        if axe_pyplot is None:
            import matplotlib.pyplot as plt
            axe_pyplot = plt.figure().add_subplot()
            axe_pyplot.set_xlim(-.6, .6)
            axe_pyplot.set_ylim(-.6, .6)

        axe_pyplot.set_title("plan gnomonic")
        axe_pyplot.set_xlabel("x.Gi (mm)")
        axe_pyplot.set_ylabel("y.Gj (mm)")


        # Affichage image de fond.
        try:
            image = self.get_image_gnomonic()
        except (NameError, AttributeError):
            pass
        else:
            *_, limits = self.experiment._get_gnomonic_matrix()
            mean, std = image.mean(), image.std()
            x_coords, y_coords = self.get_gnomonic_positions()
            axe_pyplot.imshow(image,
                origin='lower',
                aspect=((self.experiment.get_images_shape()[1]*x_coords.ptp())
                      / (self.experiment.get_images_shape()[0]*y_coords.ptp())),
                extent=limits,
                vmin=mean-2*std, vmax=mean+4*std, cmap="gray")

        # Affichage des axes.
        try:
            for axis in self.find_zone_axes():
                axe_pyplot = axis.plot_gnomonic(axe_pyplot, display=False)
        except AttributeError:
            return axe_pyplot

        # Affichage de spots.
        for spot in self:
            axe_pyplot = spot.plot_gnomonic(axe_pyplot, display=False)

        if display:
            import matplotlib.pyplot as plt
            plt.show()

        return axe_pyplot

    def plot_xy(self, axe_pyplot=None, *, display=True):
        """
        ** Prepare l'affichage du diagramme dans le plan du capteur. **

        Parameters
        ----------
        axe_pyplot : Axe
            Axe matplotlib qui supporte les methodes ``.scatter`` et ``.imshow``.
        display : boolean
            Si True, affiche a l'ecran en faisant appel a ``plt.show()``.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image)[0]
        >>>
        >>> diag.plot_xy(display=False)
        <AxesSubplot:title={'center':'plan camera'}, xlabel='x.Ci (pxl)', ylabel='y.Cj (pxl)'>
        >>>
        >>> import matplotlib.pyplot as plt
        >>> fig = plt.figure()
        >>> axe = fig.add_subplot()
        >>> diag.plot_xy(axe, display=False)
        <AxesSubplot:title={'center':'plan camera'}, xlabel='x.Ci (pxl)', ylabel='y.Cj (pxl)'>
        >>>
        """
        if axe_pyplot is None:
            import matplotlib.pyplot as plt
            axe_pyplot = plt.figure().add_subplot()

        axe_pyplot.set_title("plan camera")
        axe_pyplot.set_xlabel("x.Ci (pxl)")
        axe_pyplot.set_ylabel("y.Cj (pxl)")

        # Affichage image de fond.
        try:
            image = self.get_image_xy()
        except NameError:
            pass
        else:
            mean, std = image.mean(), image.std()
            axe_pyplot.imshow(image, vmin=mean-2*std, vmax=mean+4*std, cmap="gray")

        # Affichage des spots.
        for spot in self:
            axe_pyplot = spot.plot_xy(axe_pyplot, display=False)

        if display:
            import matplotlib.pyplot as plt
            plt.show()

        return axe_pyplot

    def predict_hkl(self, *args, **kwds):
        """
        ** Predit tous les indices hkl des spots avec un reseau de neurones. **

        Parameters
        ----------
        *args
            Same parameters as ``laue.core.hkl_nn.prediction.Predictor.__init__``.
        **kwds
            Same parameters as ``laue.core.hkl_nn.prediction.Predictor.__init__``.

        Returns
        -------
        hkl_vect : np.ndarray
            La 'liste' des indice de miller associes a chaque spot de ce diagrame.
            ``shape = (len(self), 3)``
        score : np.ndarray
            Le vecteurs des fiablilites des predictions entre 0 et 1.
            Un score > 95% assure que les indices de miller
            trouves sont correctes.
            ``shape = (len(self),)``
        """
        key = hashlib.md5(repr(args) + repr(sorted(kwds.items()))).hexdigest()
        if key not in self._hkl:
            if key not in self.experiment._predictors:
                from laue.core.hkl_nn.prediction import Predictor
                self.experiment._predictors[key] = Predictor(*args, **kwds)
            self._hkl[key] = self.experiment._predictors[key](self.get_theta_chi())
        return self._hkl[key]

    def save_file(self, filename):
        """
        ** Enregistre un fichier contenant des informations. **

        Notes
        -----
        Les extensions prises en charge sont
        ``.dat``, ``.jpg``, ``.svg``, ``.png``, ``.pk``, ``.pickle``, ``.cor``

        Parameters
        ----------
        filename : str
            Nom ou chemin du fichier de destination.
            L'extension doit etre comprise dans le nom du fichier.
            Si un fichier du meme nom existe deja, il est ecrase.

        Examples
        --------
        >>> import os, tempfile
        >>> import laue
        >>>
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> rep = tempfile.mkdtemp()
        >>> diag = laue.experiment.base_experiment.Experiment(image, config_file="laue/examples/ge_blanc.det")[0]
        >>> diag.save_file(os.path.join(rep, "ge_blanc.dat"))
        >>> diag.save_file(os.path.join(rep, "ge_blanc.jpg"))
        >>> diag.save_file(os.path.join(rep, "ge_blanc.png"))
        >>> diag.save_file(os.path.join(rep, "ge_blanc.svg"))
        >>> diag.save_file(os.path.join(rep, "ge_blanc.pk"))
        >>> diag.save_file(os.path.join(rep, "ge_blanc.cor"))
        >>>
        """
        EXT_OK = {"dat", "jpg", "jpeg", "svg", "png", "pk", "pickle", "cor"}

        assert isinstance(filename, str), \
            f"'filename' has to be a string, not a {type(filename).__name__}."
        assert "." in filename, "Le fichier doit posseder une extension."
        assert filename.split(".")[-1].lower() in EXT_OK, ("Seul les extensions "
            f"'{', '.join(EXT_OK)}' sont supportees. Pas '.{filename.split('.')[-1]}'.")

        ext = filename.split(".")[-1].lower()
        if ext == "dat":
            with open(filename, "w", encoding="utf-8") as file:
                file.write("{:<20} {:<20} {:<20}\n".format("spot_X", "spot_Y", "spot_I"))
                for spot in self:
                    file.write("{x:<20} {y:<20} {i:<20}\n".format(
                        x=spot.get_position()[0],
                        y=spot.get_position()[1],
                        i=spot.get_intensity()))
        elif ext in {"jpg", "jpeg", "svg", "png"}:
            plt = self.plot_all(display=False)
            plt.savefig(filename)
        elif ext in {"pk", "pickle"}:
            import pickle
            with open(filename, "wb") as file:
                pickle.dump(self, file)
        elif ext == "cor":
            with open(filename, "w", encoding="utf-8") as file:
                file.write((" ".join(("{:<20}",)*5) + "\n").format(
                    "2theta", "chi", "X", "Y", "I"))
                for spot in self:
                    file.write((" ".join(("{:<20}",)*5) + "\n").format(
                        2*spot.get_theta_chi()[0],
                        spot.get_theta_chi()[1],
                        spot.get_position()[0],
                        spot.get_position()[1],
                        spot.get_intensity()))

    def select_spots(self, *, n=None, sort=None):
        """
        ** Recupere une partie des spots. **

        Notes
        -----
        Les pointeurs des spots renvoyes sont dupliques, c'est une copie superficielle.
        Une suppression ou un ajout de spot dans la liste ne changera pas le diagramme
        par contre une modification d'un attribut d'un des spots va etre effectif,
        et modifira donc definitivement le spot considere.

        Parameters
        ----------
        n : int, optional
            Nombre de spots a considerer. La valeur ``None`` indique
            que tous les spots sont renvoyes.
        sort : str or callable, optional
            - None => Les spots ne sont pas tries (le plus rapide). Ils sont cedes dans
            un ordre quelquonque mais systematique. L'ordre reste inchange entre 2 appels.
            - callable => Clef de tri, qui a chaque spot de type ``laue.spot.Spot``.
            associe un flotant. Les spots ayant des petits flottant se retrouveront
            au debut, ceux avec un gros seront en fin de chaine.
            - str => La methode de tri. Il y en a plusieurs possibles:
                - "intensity" => Les spots sont renvoyes des plus intenses aux plus faibles.
                - "distortion" => Les spots sont renvoyes des plus rond aux plus biscornus.
                - "quality" => Les spots sont renvoyes des plus beau aux plus moches.

        Returns
        -------
        list
            La liste des spots. Chaque element est de type ``laue.spot.Spot``.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image)[0]
        >>> diag.select_spots(n=2, sort="intensity")
        [Spot(position=(622.09, 1656.72), quality=0.949), Spot(position=(932.05, 1214.49), quality=0.940)]
        >>> diag.select_spots(n=2, sort="distortion")
        [Spot(position=(932.05, 1214.49), quality=0.940), Spot(position=(622.09, 1656.72), quality=0.949)]
        >>> diag.select_spots(n=2, sort=lambda spot: spot.get_position()[0])
        [Spot(position=(132.03, 1204.66), quality=0.577), Spot(position=(160.35, 907.21), quality=0.621)]
        >>>
        """
        assert n is None or isinstance(n, int), f"'n' can not be {type(n).__name__}."
        assert n is None or n > 0, f"'n' can not be {n}."
        assert (sort is None or hasattr(sort, "__call__")
            or sort in {"intensity", "distortion", "quality"}), \
            f"'sort' ne peut pas etre {sort}."

        if sort is None: # Si il n'y a pas de tri a faire.
            if n is None:
                return self._spots.copy()
            return self._spots[:n]

        if hasattr(sort, "__call__"):
            l_spots = sorted(self._spots, key=sort)
        if sort in self._sorted_spots: # On enregistre la liste pour de melleur
            l_spots = self._sorted_spots[sort] #  perfs aux apels suivants.
        else:
            if sort == "intensity":
                l_spots = sorted(self._spots, key=(lambda spot: -spot.get_intensity()))
            elif sort == "distortion":
                l_spots = sorted(self._spots, key=(lambda spot: -spot.get_distortion()))
            elif sort == "quality":
                l_spots = sorted(self._spots, key=(lambda spot: -spot.get_quality()))
            self._sorted_spots[sort] = l_spots

        if n is not None:
            return l_spots[:n]
        return l_spots

    def _clean(self):
        """
        ** Supprime les attributs superfux. **

        Si les spots sont modifies, cela permet de vider la memoire
        des informations desormais fausses. Si beaucoup d'images
        sont enregistrees dans la RAM, cela permet de faire de la
        place en memoire.
        """
        if os.path.exists(self.get_id()): # Il ne faut pas supprimer
            self._image_xy = None # une image que l'on ne peut pas retrouver!
        self._quality = None
        self._image_gnom = None
        self._sorted_spots = {} # Si jamais la set_calibration ou un spot change.
        self._axes = {} # Les axes de zone depandent de beaucoup de choses, on reste donc prudent.
        self._spots_set = None # On libere de la memoire en faisant ca.
        for spot in self:
            spot._clean()

    def __contains__(self, spot):
        """
        ** Verifie qu'un spot fait bien parti de ce diagramme. **

        Parameters
        ----------
        spot : laue.spot.Spot, int
            L'instance de spot dont on cherche a savoir
            si il est present ou pas. Ou bien l'index de ce spot.

        Returns
        -------
        boolean
            True si le spot est present dans ce diagramme, False sinon.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image)[0]
        >>>
        >>> len(diag)
        78
        >>> 77 in diag
        True
        >>> 78 in diag
        False
        >>>
        >>> spot = diag[0]
        >>> spot
        Spot(position=(1370.52, 1874.78), quality=0.573)
        >>> spot in diag
        True
        >>> 
        """
        assert isinstance(spot, (Spot, int)), ("'spot' has to be an "
            f"instance of Spot or int, not {type(spot).__name__}.")

        if isinstance(spot, int):
            if spot < 0 or spot >= len(self):
                return False
            spot = self[spot]

        if self._spots_set is None:
            self._spots_set = set(self)
        return spot in self._spots_set

    def __getitem__(self, item):
        """
        ** Permet de recuperer des elements. **

        Parameters
        ----------
        items : int, slice, laue.spot.Spot, tuple
            C'est un element qui permet de choisir un ou plusieurs
            spot.s dans ce diagram de laue.

        Returns
        -------
        spots : laue.spot.Spot, list
            - L'element renvoye depend du parametre d'entree ``items``:
                - int => Renvoi le item(ieme) spot. Comme si un
                ``LaueDiagram`` etait une liste de ``laue.spot.Spot``.
                    - Type renvoye: ``laue.spot.Spot``.
                - slice => Renvoi la liste des spots compris dans
                l'intervalle fournit. Comme si ``LaueDiagram`` est aussi une liste.
                    - Type renvoye: ``list``.
                - ``laue.spot.Spot`` or tuple => equivalent a ``self.get_neighbors(item, n_max=1).pop()``.

        Raises
        ------
        IndexError
            Si aucun spot n'est candidat ou qu'on shouaite acceder a un spot qui n'existe pas.
        ValueError
            Si les arguments fournis ne sont pas conformes.
        TypeError
            Si les arguments fournis ne sont pas du bon type.

        Examples
        --------
        >>> import numpy as np
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image, config_file="laue/examples/ge_blanc.det")[0]
        >>>
        >>> type(diag[0])
        <class 'laue.spot.Spot'>
        >>> type(diag[3:22]), len(diag[3:22])
        (<class 'list'>, 19)
        >>>
        >>> diag[622, 1657]
        Spot(position=(622.09, 1656.72), quality=0.949)
        >>>
        >>> diag[0.3, 0.3]
        Spot(position=(622.09, 1656.72), quality=0.949)
        >>> np.round(diag[0.3, 0.3].get_gnomonic(), 2)
        array([0.29, 0.33])
        >>>
        """
        if isinstance(item, (int, np.integer)):
            return self._spots[item]

        if isinstance(item, slice):
            return self._spots[item]

        if isinstance(item, (Spot, tuple)):
            return self.get_neighbors(item, n_max=1).pop()

        raise ValueError("Seul les types 'int', 'slice', 'tuple' et 'Spot' sont supportes. "
            f"Or le type fourni est {type(item).__name__}.")

    def __hash__(self):
        """
        ** Fonction de hachage. **

        Permet de faire un ``dict`` ou un ``set`` avec
        des instances de ``LaueDiagram``.
        """
        return hash(self.get_id())

    def __iter__(self):
        """
        ** Permet d'iterer sur les spots. **

        Yields
        ------
        Spot
            Cede les instances des spots qui constituent
            ce diagramme dans un ordre indetermine mais invariant.
            Ces instances heritent de la classe ``laue.spot.Spot``.
            Seul les pointeurs sont cedes, ce qui implique que toute
            modification d'un spot sera globale.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image)[0]
        >>> for spot in diag:
        ...     pass
        ...
        >>>
        """
        yield from self._spots

    def __len__(self):
        """
        ** Renvoi le nombre de spots. **

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> diag = laue.experiment.base_experiment.Experiment(image)[0]
        >>> len(diag)
        78
        >>>
        """
        return len(self._spots)

    def __str__(self):
        """
        ** Renvoi une jolie representation du diagramme de Laue. **
        """
        return ("LaueDiagram:\n"
                f"    name: {self.get_id()}\n"
                f"    nbr spots: {len(self.select_spots())}\n"
                f"    quality: {self.get_quality()}")

    def __repr__(self):
        """
        ** Renvoi une chaine evaluable de self. **
        """
        return ("LaueDiagram("
                f"name={repr(self.get_id())})")
