import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import KNeighborsRegressor,NearestNeighbors
from sklearn.ensemble import ExtraTreesRegressor,HistGradientBoostingRegressor
from sklearn.multioutput import MultiOutputRegressor
from .features import feature_columns,baseline,labels


class ParameterModel:
    """Positive waveform parameters; residual formulation predicts log-ratios.

    All learned transforms are fit on training rows only. Separate models are
    used for impulse type, topology, and source domain.
    """
    def __init__(self,domain,formulation,family):
        self.domain,self.formulation,self.family=domain,formulation,family
        self.columns=feature_columns(domain,formulation)

    def fit(self,frame):
        x=frame[self.columns].to_numpy(float);y=labels(frame,self.domain)
        if not np.isfinite(x).all() or (x<0).any() or not np.isfinite(y).all() or (y<=0).any():
            raise ValueError("Invalid inputs or regression targets")
        self.x_scaler=StandardScaler().fit(np.log1p(x))
        target=np.log(y/baseline(frame,self.domain)) if self.formulation=="residual" else np.log(y)
        self.y_scaler=StandardScaler().fit(target)
        if self.family=="knn":
            self.estimator=KNeighborsRegressor(n_neighbors=7,weights="distance",n_jobs=1)
        elif self.family=="extra_trees":
            self.estimator=ExtraTreesRegressor(n_estimators=128,min_samples_leaf=2,max_features=1.,random_state=90210,n_jobs=1)
        elif self.family=="hist_gradient_boosting":
            self.estimator=MultiOutputRegressor(HistGradientBoostingRegressor(max_iter=180,max_leaf_nodes=15,min_samples_leaf=10,l2_regularization=1.,learning_rate=.06,early_stopping=False,random_state=90210),n_jobs=1)
        else:raise ValueError(self.family)
        z=self.x_scaler.transform(np.log1p(x))
        self.estimator.fit(z,self.y_scaler.transform(target))
        self.minimum=x.min(axis=0);self.maximum=x.max(axis=0)
        self.neighbors=NearestNeighbors(n_neighbors=2).fit(z)
        d=self.neighbors.kneighbors(z)[0][:,1]
        self.ood_radius=float(np.quantile(d,.99)*1.5)
        self.seen_stages=set(frame["Stages" if self.domain=="legacy" else "stages"].tolist())
        self.seen_fronts=set(frame["Front_R_Stage" if self.domain=="legacy" else "front_per_stage_ohm"].tolist())
        if self.domain!="legacy":
            self.seen_tails=set(frame["tail_per_stage_ohm"].tolist())
            self.seen_parallel=set(frame["tail_parallel"].tolist())
        return self

    def predict(self,frame):
        x=frame[self.columns].to_numpy(float)
        if not np.isfinite(x).all() or (x<0).any():raise ValueError("Nonfinite or negative model input")
        z=self.x_scaler.transform(np.log1p(x))
        raw=self.y_scaler.inverse_transform(self.estimator.predict(z))
        with np.errstate(over="raise",invalid="raise"):
            pred=np.exp(raw)
        return pred*baseline(frame,self.domain) if self.formulation=="residual" else pred

    def ood(self,frame):
        x=frame[self.columns].to_numpy(float)
        slack=1e-10*np.maximum(1,abs(self.maximum))
        outside=((x<self.minimum-slack)|(x>self.maximum+slack)).any(axis=1)
        dist=self.neighbors.kneighbors(self.x_scaler.transform(np.log1p(x)),n_neighbors=1)[0][:,0]
        stage=frame["Stages" if self.domain=="legacy" else "stages"].isin(self.seen_stages).to_numpy()
        front=frame["Front_R_Stage" if self.domain=="legacy" else "front_per_stage_ohm"].isin(self.seen_fronts).to_numpy()
        tail=np.ones(len(frame),dtype=bool)
        if self.domain!="legacy":
            tail=frame.tail_per_stage_ohm.isin(self.seen_tails).to_numpy() & frame.tail_parallel.isin(self.seen_parallel).to_numpy()
        return outside|(dist>self.ood_radius)|~stage|~front|~tail
