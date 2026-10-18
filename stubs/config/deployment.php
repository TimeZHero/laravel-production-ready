<?php

use Illuminate\Support\Str;

$tag = env('GIT_TAG');
$tagged = is_string($tag) && $tag !== '';

$release = env('COMMIT_SHA');

if ($tagged) {
    $package = Str::of((string) env('APP_NAME', 'laravel'))->slug();
    $version = Str::of($tag)->ltrim('v');

    $release = "{$package}@{$version}";
}

return [

    /*
    | The release is either semver or the commit SHA.
    */

    'release' => $release,

    'commit' => env('COMMIT_SHA'),

    'tag' => $tagged ? $tag : null,

    'branch' => env('BRANCH'),

];
