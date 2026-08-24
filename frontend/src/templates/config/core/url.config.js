const backendUrl = (process.env.MEDIACMS_URL || '').replace(/\/+$/, '');

module.exports = {
  home: './index.html',
  search: './search.html',
  latestMedia: './latest.html',
  featuredMedia: './featured.html',
  recommendedMedia: './recommended.html',
  members: './members.html',
  /* Error pages */
  error404: './error.html',
  /* Archive pages */
  tags: './tags.html',
  categories: './categories.html',
  /* User pages */
  likedMedia: './liked.html',
  history: './history.html',
  /* Add pages */
  addMedia: './add-media.html',
  /* Profile/account edit pages */
  editProfile: './edit-profile.html',
  editChannel: './edit-channel.html',
  /* User account pages */
  signin: backendUrl + '/accounts/login/',
  signout: backendUrl + '/accounts/logout/',
  register: backendUrl + '/accounts/signup/',
  changePassword: backendUrl + '/accounts/password/change/',
  /* Administration pages */
  admin: '/admin',
  /* Management pages */
  manageMedia: './manage-media.html',
  manageUsers: './manage-users.html',
  manageComments: './manage-comments.html',
};
