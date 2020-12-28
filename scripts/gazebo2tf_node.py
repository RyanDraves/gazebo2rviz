#!/usr/bin/env python3

from __future__ import print_function

import rospy
import tf
from geometry_msgs.msg import Pose
from gazebo_msgs.msg import LinkStates
import tf_conversions.posemath as pm
from tf.transformations import *

import pysdf

tfBroadcaster = None
submodelsToBeIgnored = []
lastUpdateTime = None
updatePeriod = 0.05
model_cache = {}
prev_time = 0.0


def is_ignored(link_name):
  for ignored_submodel in submodelsToBeIgnored:
    if link_name.startswith(ignored_submodel + '::'):
      return True
  return False


def on_link_states_msg(link_states_msg):
  """
  Publish tf for each model in current Gazebo world
  """
  global lastUpdateTime
  sinceLastUpdateDuration = rospy.get_rostime() - lastUpdateTime
  if sinceLastUpdateDuration.to_sec() < updatePeriod:
    return
  lastUpdateTime = rospy.get_rostime()

  poses = {'gazebo_world': identity_matrix()}
  for (link_idx, link_name) in enumerate(link_states_msg.name):
    poses[link_name] = pysdf.pose_msg2homogeneous(link_states_msg.pose[link_idx])
    #print('%s:\n%s' % (link_name, poses[link_name]))

  global prev_time
  cur_time = rospy.get_rostime()
  repeated_timestamp = (cur_time == prev_time)
  prev_time = cur_time

  for (link_idx, link_name) in enumerate(link_states_msg.name):
    #print(link_idx, link_name)
    modelinstance_name = link_name.split('::')[0]
    #print('modelinstance_name:', modelinstance_name)
    model_name = pysdf.name2modelname(modelinstance_name)
    # print('tf model_name:', model_name)
    if not model_name in model_cache:
      sdf = pysdf.SDF(model=model_name)
      for model in sdf.world.models:
        if model.name == model_name:
          model_cache[model_name] = model
          break
      # model_cache[model_name] = sdf.world.models[0] if len(sdf.world.models) >= 1 else None
      if model_cache[model_name]:
        rospy.loginfo('[GAZEBO2TF] Loaded model: %s' % model_cache[model_name].name)
      else:
        rospy.loginfo('[GAZEBO2TF] Unable to load model: %s' % model_name)
    model = model_cache[model_name]
    link_name_in_model = link_name.replace(modelinstance_name + '::', '')
    if model:
      link = model.get_link(link_name_in_model)
      if link.tree_parent_joint:
        parent_link = link.tree_parent_joint.tree_parent_link
        parent_link_name = parent_link.get_full_name()
        #print('parent:', parent_link_name)
        parentinstance_link_name = parent_link_name.replace(model_name, modelinstance_name, 1)
      else: # direct child of world
        parentinstance_link_name = 'gazebo_world'
    else: # Not an SDF model
        # print("tf not a model")
        parentinstance_link_name = 'gazebo_world'
    #print('parentinstance:', parentinstance_link_name)
    if is_ignored(parentinstance_link_name):
      rospy.loginfo("[GAZEBO2TF] Ignoring TF %s -> %s" % (parentinstance_link_name, link_name))
      continue
    pose = poses[link_name]
    # print("Pose: {}".format(pose))
    parent_pose = poses[parentinstance_link_name]
    rel_tf = concatenate_matrices(inverse_matrix(parent_pose), pose)
    translation, quaternion = pysdf.homogeneous2translation_quaternion(rel_tf)
    #print('Publishing TF %s -> %s: t=%s q=%s' % (pysdf.sdf2tfname(parentinstance_link_name), pysdf.sdf2tfname(link_name), translation, quaternion))
    # Don't republish transforms of the same timestamp
    # https://github.com/ros/geometry2/issues/467
    if not rospy.is_shutdown() and not repeated_timestamp:
      tfBroadcaster.sendTransform(translation, quaternion, cur_time, pysdf.sdf2tfname(link_name), pysdf.sdf2tfname(parentinstance_link_name))



def main():
  rospy.init_node('gazebo2tf')

  global submodelsToBeIgnored
  submodelsToBeIgnored = rospy.get_param('~ignore_submodels_of', '').split(';')
  rospy.loginfo('[GAZEBO2TF] Ignoring submodels of: ' + str(submodelsToBeIgnored))

  global tfBroadcaster
  tfBroadcaster = tf.TransformBroadcaster()

  global lastUpdateTime
  lastUpdateTime = rospy.get_rostime()
  linkStatesSub = rospy.Subscriber('gazebo/link_states', LinkStates, on_link_states_msg)

  rospy.loginfo('[GAZEBO2TF] Spinning')
  rospy.spin()

if __name__ == '__main__':
  main()
