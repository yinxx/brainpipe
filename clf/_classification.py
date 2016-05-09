import numpy as n

from sklearn.discriminant_analysis import (LinearDiscriminantAnalysis,
                                           QuadraticDiscriminantAnalysis)
from sklearn.svm import SVC, LinearSVC, NuSVC
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.cross_validation import (StratifiedKFold, KFold,
                                      StratifiedShuffleSplit, ShuffleSplit)
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.base import clone

from joblib import Parallel, delayed

from brainpipe.statistics import binostatinv, perm2pval, permIntraClass
from brainpipe.tools import groupInList, list2index
from brainpipe.sys.tools import adaptsize

from itertools import product

__all__ = ['classify',
           'defClf',
           'defCv',
           'generalization'
           ]


class classify(object):
    """Define a classification object and apply to classify data.
    This class can be consider as a centralization of scikit-learn
    tools, with a few more options.

    To classify data, two objects are necessary :
    - A classifier object (lda, svm, knn...)
    - A cross-validation object which is used to validate a classification
    performance.
    This two objects can either be defined before the classify object with
    defCv and defClf, or they can be directly defined inside the classify
    class.

    Args:
        y: array
            The vector label

    Kwargs:
        clf: int / string / classifier object, optional, [def: 0]
            Define a classifier. If clf is an integer or a string, the
            classifier will be defined inside classify. Otherwise, it is
            possible to define a classifier before with defClf and past it in clf.

        cvtype: string / cross-validation object, optional, [def: 'skfold']
            Define a cross-validation. If cvtype is a string, the
            cross-validation will be defined inside classify. Otherwise, it is
            possible to define a cross-validation before with defCv and past it
            in cvtype.

        clfArg: dictionnary, optional, [def: {}]
            This dictionnary can be used to define supplementar arguments for the
            classifier. See the documentation of defClf.

        cvArg: dictionnary, optional, [def: {}]
            This dictionnary can be used to define supplementar arguments for the
            cross-validation. See the documentation of defCv.

    Example:
        >> ># 1) Define a classifier and a cross-validation before classify():

            >>> # Define a 50 times 5-folds cross-validation :
            >>> cv = defCv(y, cvtype='kfold', rep=50, n_folds=5)
            >>> # Define a Random Forest with 200 trees :
            >>> clf = defClf(y, clf='rf', n_tree=200, random_state=100)
            >>> # Past the two objects inside classify :
            >>> clfObj = classify(y, clf=clf, cvtype=cv)

        >>> # 2) Define a classifier and a cross-validation inside classify():
            >>> clfObj = classify(y, clf = 'rf', cvtype = 'kfold',
            ...        clfArg = {'n_tree':200, 'random_state':100},
            ...                  cvArg = {'rep':50, 'n_folds':5})
        >>> # 1) and 2) are equivalent. Then use clfObj.fit() to classify data.
    """

    def __init__(self, y, clf='lda', cvtype='skfold', clfArg={}, cvArg={}):

        self.y = y

        # Define clf if it's not defined :
        if isinstance(clf, (int, str)):
            clf = defClf(y, clf=clf, **clfArg)
        self.clf = clf

        # Define cv if it's not defined :
        if isinstance(cvtype, str):
            cvtype = defCv(y, cvtype=cvtype, **cvArg)
        self.cv = cvtype

    def __str__(self):
        return str(self.cv[0].lgStr)+' with a '+str(self.clf.lgStr)

    def fit(self, x, mf=False, center=False, grp=n.array([]), n_jobs=-1):
        """Apply the classification and cross-validation objects to the array x.
        this method return an array containing the decoding accuracy. The
        dimension of this arry depend of the input x.

        Args:
            x: array
                Data to classify. Consider that x.shape = (N, M), N is the number
                of trials (which should be the length of y). M, the number of
                colums, is a supplementar dimension for classifying data. If M = 1,
                the data is consider as a single feature. If M > 1, use the
                parameter mf to say if x should be consider as a single feature
                (mf=False) or multi-features (mf=True)

        Kargs:
            mf: bool, optional, [def: False]
                If mf=False, the returned decoding accuracy (da) will have a
                shape of (1, rep) where rep, is the number of repetitions.
                This mean that all the features are used together. If mf=True,
                da.shape = (M, rep), where M is the number of columns of x.

            center: optional, bool, [def: False]
                Normalize fatures with a zero mean by substracting then dividing
                by the mean. The center parameter should be set to True if the
                classifier is a svm.

            grp: array, optional, [def: array()]
                If mf=True, the grp parameter allow to define group of features.
                If x.shape = (N, 5) and grp=n.array([0,0,1,2,1]), this mean that
                3 groups of features will be considered : (0,1,2)

            n_jobs: integer, optional, [def: -1]
                Control the number of jobs to cumpute the decoding accuracy. If
                n_jobs = -1, all the jobs are used.

        Return:
            da: array
                The decoding accuracy.
        """
        da, _, _, self._ytrue, self._ypred = _fit(x, self.y, self.clf, self.cv,
                                                  mf, grp, center, n_jobs)
        return da

    def fit_stat(self, x, mf=False, center=False, grp=n.array([]),
                 method='bino', n_perm=200, rndstate=0, n_jobs=-1):
        """Evaluate the statistical significiancy of the decoding accuracy.

        Args:
            x: array
                Data to classify. Consider that x.shape = (N, M), N is the number
                of trials (which should be the length of y). M, the number of
                colums, is a supplementar dimension for classifying data. If M = 1,
                the data is consider as a single feature. If M > 1, use the
                parameter mf to say if x should be consider as a single feature
                (mf=False) or multi-features (mf=True)

        Kargs:
            mf: bool, optional, [def: False]
                If mf=False, the returned decoding accuracy (da) will have a
                shape of (1, rep) where rep, is the number of repetitions.
                This mean that all the features are used together. If mf=True,
                da.shape = (M, rep), where M is the number of columns of x.

            center: optional, bool, [def: False]
                Normalize fatures with a zero mean by substracting then dividing
                by the mean. The center parameter should be set to True if the
                classifier is a svm.

            grp: array, optional, [def: array()]
                If mf=True, the grp parameter allow to define group of features.
                If x.shape = (N, 5) and grp=n.array([0,0,1,2,1]), this mean that
                3 groups of features will be considered : (0,1,2)

            method: string, optional, [def: 'bino']
                Four methods are implemented to test the statistical significiance
                of the decoding accuracy :

                    - 'bino': binomial test
                    - 'label_rnd': randomly shuffle the labels
                    - 'full_rnd': randomly shuffle the whole array x
                    - 'intra_rnd': randomly shuffle x inside each class and each feature

                Methods 2, 3 and 4 are based on permutations. The method 2 and 3
                should provide similar results. But 4 should be more conservative.

            n_perm: integer, optional, [def: 200]
                Number of permutations for the methods 2, 3 and 4

            rndstate: integer, optional, [def: 0]
                Fix the random state of the machine. Usefull to reproduce results.

            n_jobs: integer, optional, [def: -1]
                Control the number of jobs to cumpute the decoding accuracy. If
                n_jobs = -1, all the jobs are used.

        Return:
            da: array
                The decoding accuracy.

            pvalue: array
                Array of associated pvalue

            daPerm: array
                Array of all the decodings obtained for each permutations.


    .. rubric:: Footnotes
    .. [#f1] Ojala and Garriga, 2010 `see <http://www.jmlr.org/papers/volume11/ojala10a/ojala10a.pdf>`_
    .. [#f2] Combrisson and Jerbi, 2015 `see <http://www.ncbi.nlm.nih.gov/pubmed/25596422/>`_

        """
        # Get the current da
        da, x, y, self._ytrue, self._ypred = _fit(x, self.y, self.clf,
                                                  self.cv, mf, grp, center,
                                                  n_jobs)
        score = n.array([n.mean(k) for k in da])
        rndstate = n.random.RandomState(rndstate)

        # -------------------------------------------------------------
        # Binomial :
        # -------------------------------------------------------------
        if method == 'bino':
            pvalue = binostatinv(self.y, score)
            daPerm = n.array([])

        # -------------------------------------------------------------
        # Permutations :
        # -------------------------------------------------------------
        elif method.lower().find('_rnd')+1:

            # Generate idx tricks :
            claIdx, listPerm, listFeat = list2index(n_perm, len(x))

            # -> Shuffle the labels :
            if method == 'label_rnd':
                y_sh = [rndstate.permutation(y) for k in range(n_perm)]
                cvs = Parallel(n_jobs=n_jobs)(delayed(_cvscore)(
                        x[k[1]], y_sh[k[0]], clone(self.clf), self.cv[0])
                        for k in claIdx)

            # -> Full randomization :
            elif method == 'full_rnd':
                cvs = Parallel(n_jobs=n_jobs)(delayed(_cvscore)(
                        rndstate.permutation(x[k[1]]), y, clone(self.clf),
                        self.cv[0]) for k in claIdx)

            # -> Shuffle intra-class :
            elif method == 'intra_rnd':
                cvs = Parallel(n_jobs=n_jobs)(delayed(_cvscore)(
                        permIntraClass(x[k[1]], y, k[0]), y, clone(self.clf),
                        self.cv[0]) for k in claIdx)

            # Reconstruct daPerm and get the associated p-value:
            daPerm, _, _ = zip(*cvs)
            daPerm = n.array(groupInList(daPerm, listFeat))
            pvalue = perm2pval(score, daPerm)

        else:
            raise ValueError('No statistical method '+method+' found')

        return da, n.array(pvalue), daPerm

    def confusion_matrix(self, x, mf=False, center=False, grp=n.array([]),
                         n_jobs=-1, normalize=True, update=True):
        """Get confusion matrix.

        Args:
            x: array
                Data to classify. Consider that x.shape = (N, M), N is the number
                of trials (which should be the length of y). M, the number of
                colums, is a supplementar dimension for classifying data. If M = 1,
                the data is consider as a single feature. If M > 1, use the
                parameter mf to say if x should be consider as a single feature
                (mf=False) or multi-features (mf=True)

        Kargs:
            mf: bool, optional, [def: False]
                If mf=False, the returned decoding accuracy (da) will have a
                shape of (1, rep) where rep, is the number of repetitions.
                This mean that all the features are used together. If mf=True,
                da.shape = (M, rep), where M is the number of columns of x.

            center: optional, bool, [def: False]
                Normalize fatures with a zero mean by substracting then dividing
                by the mean. The center parameter should be set to True if the
                classifier is a svm.

            grp: array, optional, [def: array()]
                If mf=True, the grp parameter allow to define group of features.
                If x.shape = (N, 5) and grp=n.array([0,0,1,2,1]), this mean that
                3 groups of features will be considered : (0,1,2)

            n_jobs: integer, optional, [def: -1]
                Control the number of jobs to cumpute the decoding accuracy. If
                n_jobs = -1, all the jobs are used.

            normalize: bool, optional, [def: True]
                Normalize or not the confusion matrix

            update: bool, optional, [def: True]
                If update is True, the data will be re-classified. But, if update
                is set to False, and if the methods .fit() or .fit_stat() have been
                run before, the data won't we re-classified. Instead, the labels
                previously found will be used to get confusion matrix.

        Return:
            A list of confusion matrix, depending of the size of x.
        """
        # Re-classify data or use the already existing labels :
        if update:
            _, _, _, self._ytrue, self._ypred = _fit(x, self.y, self.clf,
                                                     self.cv, mf, grp, center,
                                                     n_jobs)
        else:
            if not ((hasattr(self, '_ytrue')) and (hasattr(self, '_ypred'))):
                raise ValueError("No labels found. Please either run .fit()"
                                 "or .fit_stat() before or set update=True")

        # Get variables and compute confusion matrix:
        y_pred, y_true = self._ypred, self._ytrue
        nfeat, nrep = len(y_true), len(y_true[0])
        cm = [n.mean(n.array([confusion_matrix(y_true[k][i], y_pred[
            k][i]) for i in range(nrep)]), 0) for k in range(nfeat)]

        # Normalize the confusion matrix :
        if normalize:
            cm = [100*k/k.sum(axis=1)[:, n.newaxis] for k in cm]

        return cm


def _fit(x, y, clf, cv, mf, grp, center, n_jobs):
    """Sub function for fitting
    """
    # Check the inputs size :
    x, y = checkXY(x, y, mf, grp, center)
    rep, nfeat = len(cv), len(x)

    # Tricks : construct a list of tuple containing the index of
    # (repetitions,features) & loop on it. Optimal for parallel computing :
    claIdx, listRep, listFeat = list2index(rep, nfeat)

    # Run the classification :
    cvs = Parallel(n_jobs=n_jobs)(delayed(_cvscore)(
        x[k[1]], y, clone(clf), cv[k[0]]) for k in claIdx)
    da, y_true, y_pred = zip(*cvs)

    # Reconstruct elements :
    da = n.array(groupInList(da, listFeat))
    y_true = groupInList(y_true, listFeat)
    y_pred = groupInList(y_pred, listFeat)

    return da, x, y, y_true, y_pred


def _cvscore(x, y, clf, cvS):
    """Get the decoding accuracy of one cross-validation
    """
    y_pred = []
    y_true = []
    for trainidx, testidx in cvS:
        xtrain, xtest = x[trainidx, ...], x[testidx, ...]
        ytrain, ytest = y[trainidx, ...], y[testidx, ...]
        clf.fit(xtrain, ytrain)
        y_pred.extend(clf.predict(xtest))
        y_true.extend(ytest)
    return 100*accuracy_score(y_true, y_pred), y_true, y_pred


class defClf(object):

    """Choose a classifier and switch easyly between classifiers
    implemented in scikit-learn.

    Args:
        y: array
            The vector label

    clf: int or string, optional, [def: 0]
        Define a classifier. Use either an integer or a string
        Choose between:

            - 0 / 'lda': Linear Discriminant Analysis (LDA)
            - 1 / 'svm': Support Vector Machine (SVM)
            - 2 / 'linearsvm' : Linear SVM
            - 3 / 'nusvm': Nu SVM
            - 4 / 'nb': Naive Bayesian
            - 5 / 'knn': k-Nearest Neighbor
            - 6 / 'rf': Random Forest
            - 7 / 'lr': Logistic Regression
            - 8 / 'qda': Quadratic Discriminant Analysis

    kern: string, optional, [def: 'rbf']
        Kernel of the 'svm' classifier

    n_knn: int, optional, [def: 10]
        Number of neighbors for the 'knn' classifier

    n_tree: int, optional, [def: 100]
        Number of trees for the 'rf' classifier

    Kargs:
        optional arguments. To define other parameters, see the description of
        scikit-learn.

    Return:
        A scikit-learn classification objects with two supplementar arguments :

            - lgStr : long description of the classifier
            - shStr : short description of the classifier
    """

    def __init__(self, y, clf='lda', kern='rbf', n_knn=10, n_tree=100,
                 priors=False, **kwargs):
        pass

    def __str__(self):
        return self.lgStr

    def __new__(self, y, clf='lda', kern='rbf', n_knn=10, n_tree=100,
                priors=False, **kwargs):

        # Default value for priors :
        priors = n.array([1/len(n.unique(y))]*len(n.unique(y)))

        if isinstance(clf, str):
            clf = clf.lower()

        # LDA :
        if clf == 'lda' or clf == 0:
            clfObj = LinearDiscriminantAnalysis(
                priors=priors, **kwargs)
            clfObj.lgStr = 'Linear Discriminant Analysis'
            clfObj.shStr = 'LDA'

        # SVM : ‘linear’, ‘poly’, ‘rbf’, ‘sigmoid’, ‘precomputed’ or a callable
        elif clf == 'svm' or clf == 1:
            clfObj = SVC(kernel=kern, probability=True, **kwargs)
            clfObj.lgStr = 'Support Vector Machine (kernel=' + kern + ')'
            clfObj.shStr = 'SVM-' + kern

        # Linear SVM:
        elif clf == 'linearsvm' or clf == 2:
            clfObj = LinearSVC(**kwargs)
            clfObj.lgStr = 'Linear Support Vector Machine'
            clfObj.shStr = 'LSVM'

        # Nu SVM :
        elif clf == 'nusvm' or clf == 3:
            clfObj = NuSVC(**kwargs)
            clfObj.lgStr = 'Nu Support Vector Machine'
            clfObj.shStr = 'NuSVM'

        # Naive Bayesian :
        elif clf == 'nb' or clf == 4:
            clfObj = GaussianNB(**kwargs)
            clfObj.lgStr = 'Naive Baysian'
            clfObj.shStr = 'NB'

        # KNN :
        elif clf == 'knn' or clf == 5:
            clfObj = KNeighborsClassifier(n_neighbors=n_knn, **kwargs)
            clfObj.lgStr = 'k-Nearest Neighbor (neighbor=' + str(n_knn) + ')'
            clfObj.shStr = 'KNN-' + str(n_knn)

        # Random forest :
        elif clf == 'rf' or clf == 6:
            clfObj = RandomForestClassifier(n_estimators=n_tree, **kwargs)
            clfObj.lgStr = 'Random Forest (tree=' + str(n_tree) + ')'
            clfObj.shStr = 'RF-' + str(n_tree)

        # Logistic regression :
        elif clf == 'lr' or clf == 7:
            clfObj = LogisticRegression(**kwargs)
            clfObj.lgStr = 'Logistic Regression'
            clfObj.shStr = 'LogReg'

        # QDA :
        elif clf == 'qda' or clf == 8:
            clfObj = QuadraticDiscriminantAnalysis(**kwargs)
            clfObj.lgStr = 'Quadratic Discriminant Analysis'
            clfObj.shStr = 'QDA'

        else:
            raise ValueError('No classifier "'+str(clf)+'"" found')

        return clfObj


class defCv(object):

    """Choose a cross_validation (CV) and switch easyly between
    CV implemented in scikit-learn.

    Args:
        y: array
            The vector label

    kargs:
        cvtype: string, optional, [def: skfold]
            Define a cross_validation. Choose between :

                - 'skfold': Stratified k-Fold
                - 'kfold': k-fold
                - 'sss': Stratified Shuffle Split
                - 'ss': Shuffle Split

        n_folds: integer, optional, [def: 10]
            Number of folds

        rndstate: integer, optional, [def: 0]
            Define a random state. Usefull to replicate a result

        rep: integer, optional, [def: 10]
            Number of repetitions

        kwargs: optional arguments. To define other parameters,
        see the description of scikit-learn.

    Return:
        A list of scikit-learn cross-validation objects with two supplementar
        arguments:

            - lgStr: long description of the cross_validation
            - shStr: short description of the cross_validation
    """

    def __init__(self, y, cvtype='skfold', n_folds=10, rndstate=0, rep=10,
                 **kwargs):
        pass

    def __str__(self):
        return self.lgStr

    def __new__(self, y, cvtype='skfold', n_folds=10, rndstate=0, rep=10,
                **kwargs):
        y = n.ravel(y)
        return [_define(y, cvtype=cvtype, n_folds=n_folds, rndstate=k, rep=rep,
                        **kwargs) for k in range(rep)]


def _define(y, cvtype='skfold', n_folds=10, rndstate=0, rep=10,
            **kwargs):
    # Stratified k-fold :
    if cvtype == 'skfold':
        cvT = StratifiedKFold(y, n_folds=n_folds, shuffle=True,
                              random_state=rndstate, **kwargs)
        cvT.lgStr = str(rep)+'-times, '+str(n_folds)+' Stratified k-folds'
        cvT.shStr = str(rep)+' rep x'+str(n_folds)+' '+cvtype

    # k-fold :
    elif cvtype == 'kfold':
        cvT = KFold(len(y), n_folds=n_folds, shuffle=True,
                    random_state=rndstate, **kwargs)
        cvT.lgStr = str(rep)+'-times, '+str(n_folds)+' k-folds'
        cvT.shStr = str(rep)+' rep x'+str(n_folds)+' '+cvtype

    # Shuffle stratified k-fold :
    elif cvtype == 'sss':
        cvT = StratifiedShuffleSplit(y, n_iter=n_folds,
                                     test_size=1/n_folds,
                                     random_state=rndstate, **kwargs)
        cvT.lgStr = str(rep)+'-times, test size 1/' + \
            str(n_folds)+' Shuffle Stratified Split'
        cvT.shStr = str(rep)+' rep x'+str(n_folds)+' '+cvtype

    # Shuffle stratified :
    elif cvtype == 'ss':
        cvT = ShuffleSplit(len(y), n_iter=rep, test_size=1/n_folds,
                           random_state=rndstate, **kwargs)
        cvT.lgStr = str(rep)+'-times, test size 1/' + \
            str(n_folds)+' Shuffle Stratified'
        cvT.shStr = str(rep)+' rep x'+str(n_folds)+' '+cvtype

    else:
        raise ValueError('No cross-validation "'+cvtype+'"" found')

    return cvT


def checkXY(x, y, mf, grp, center):
    """Prepare the inputs x and y
    x.shape = (ntrials, nfeat)
    """
    x, y = n.matrix(x), n.ravel(y)
    if x.shape[0] != len(y):
        x = x.T

    # Normalize features :
    if center:
        x_m = n.tile(n.mean(x, 0), (x.shape[0], 1))
        x = (x-x_m)/x_m

    # Group parameter :
    if mf:
        if not isinstance(grp, n.ndarray):
            grp = n.ravel(grp)
        if grp.size == 0:
            x = [x]
        elif (grp.size != 0) and (grp.size == x.shape[1]):
            ugrp = list(set(grp))
            x = [n.array(x[:, n.where(grp == k)[0]]) for k in ugrp]
        elif (grp.size != 0) and (grp.size != x.shape[1]):
            raise ValueError('The grp parameter must have the same size as the'
                             ' number of features ('+str(x.shape[1])+')')
    else:
        x = [n.array(x[:, k]) for k in range(x.shape[1])]

    return x, y


class generalization(object):
    """Generalize the decoding performance of features.
    The generalization consist of training and testing at diffrents
    moments. The use is to see if a feature is consistent and performant
    in diffrents period of time.

    Args:
        time: array/list
            The time vector of dimension npts

        y: array
            The vector label of dimension ntrials

        x: array
            The data to generalize. If x is a 2D array, the dimension of x
            should be (ntrials, npts). If x is 3D array, the third dimension
            is consider as multi-features. This can be usefull to do time
            generalization in multi-features.

    Kargs:
        clf: int / string / classifier object, optional, [def: 0]
            Define a classifier. If clf is an integer or a string, the
            classifier will be defined inside classify. Otherwise, it is
            possible to define a classifier before with defClf and past it in clf.

        cvtype: string / cross-validation object, optional, [def: None]
            Define a cross-validation. If cvtype is None, the diagonal of the
            matrix of decoding accuracy will be set at zero. If cvtype is defined,
            a cross-validation will be performed on the diagonal. If cvtype is a
            string, the cross-validation will be defined inside classify.
            Otherwise, it is possible to define a cross-validation before with
            defCv and past it in cvtype.

        clfArg: dictionnary, optional, [def: {}]
            This dictionnary can be used to define supplementar arguments for the
            classifier. See the documentation of defClf.

        cvArg: dictionnary, optional, [def: {}]
            This dictionnary can be used to define supplementar arguments for the
            cross-validation. See the documentation of defCv.

    Return:
        An array of dimension (npts, npts) containing the decoding accuracy. The y
        axis is the training time and the x axis is the testing time (also known
        as "generalization time")
    """
    def __init__(time, y, x, clf='lda', cvtype=None, clfArg={},
                 cvArg={}):
        pass

    def __new__(self, time, y, x, clf='lda', cvtype=None, clfArg={},
                cvArg={}):

        self.y = n.ravel(y)
        self.time = time

        # Define clf if it's not defined :
        if isinstance(clf, (int, str)):
            clf = defClf(y, clf=clf, **clfArg)
        self.clf = clf

        # Define cv if it's not defined :
        if isinstance(cvtype, str) and (cvtype is not None):
            cvtype = defCv(y, cvtype=cvtype, rep=1, **cvArg)
        self.cv = cvtype
        if isinstance(cvtype, list):
            cvtype = cvtype[0]

        # Check the size of x:
        npts, ntrials = len(time), len(y)
        if len(x.shape) == 2:
            x = n.matrix(x)
        x = adaptsize(x, (2, 0, 1))

        da = n.zeros([npts, npts])
        # Training dimension
        for k in range(npts):
            xx = x[k, ...]
            # Testing dimension
            for i in range(npts):
                xy = x[i, ...]
                # If cv is defined, do a cv on the diagonal
                if (k == i) and (cvtype is not None):
                    da[i, k] = _cvscore(xx, y, clf, cvtype)[0]/100
                # If cv is not defined, let the diagonal at zero
                elif (k == i) and (cvtype is None):
                    pass
                else:
                    da[i, k] = accuracy_score(y, clf.fit(xx, y).predict(xy))
        return 100*da
