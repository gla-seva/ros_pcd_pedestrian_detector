#!/usr/bin/env python

import numpy as np
import open3d
import torch
import os
import time

import config
from tools import preprocess
from tools import dataloader_tools as data_loader
from model import Unet as models


import rospy
import ros_numpy

import sensor_msgs.point_cloud2 as pc2
from sensor_msgs.msg import PointCloud2, PointField

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

pub = None
model = None

def model_loader(model_path):
    model = models.ResNetUNet(1)
    if torch.cuda.is_available():
        model.to(device)
        model.load_state_dict(torch.load(model_path))
    else:
        model.load_state_dict(torch.load(model_path, map_location='cpu'))
    model.eval()
    return model


def callback(cloud_msg):
    cloud_arr = ros_numpy.point_cloud2.pointcloud2_to_array(cloud_msg)
    xyz = ros_numpy.point_cloud2.get_xyz_points(cloud_arr, dtype=np.float32)

    pcd2img = preprocess.Pcd2ImageTransform().fit_fast(xyz)
    data = pcd2img.transform_fast()

    # data = data_loader.interp_data(data, data[:,:,3] != 0)
    p, n = data_loader.pointnetize(data[:,:,0:4], n_size=[3,3])

    p = torch.tensor(p, dtype=torch.float).permute(-1, -2, 0, 1).to(device)
    n = torch.tensor(n, dtype=torch.float).permute(-1, -2, 0, 1).to(device)

    pred = model(p[None, 0:4, ...], n[None, 0:3, ...]).sigmoid()

    xyzp = pcd2img.inverse_transform((pred.detach().cpu().numpy()[0, 0, :, :] > 0.5).astype(np.float32)).copy()
    dt = np.dtype({'names':['x','y','z', 'probability'], 'formats':[np.float32, np.float32, np.float32, np.float32]})
    cloud_arr_new = np.frombuffer(xyzp.data, dtype=dt)

    cloud_msg_prob = ros_numpy.point_cloud2.array_to_pointcloud2(cloud_arr_new, frame_id='velodyne')
    pub.publish(cloud_msg_prob)

if __name__ == '__main__':
    model = model_loader("src/pcd_semantic_segmentation/scripts/model/UNet_best.pth")
    rospy.init_node('pedestrian_detector', anonymous=True)
    pub = rospy.Publisher('velodyne_points_pedestrians', PointCloud2, queue_size=10)
    rospy.Subscriber('velodyne_points', PointCloud2, callback, queue_size=1, buff_size=2**24)
    rospy.spin()
