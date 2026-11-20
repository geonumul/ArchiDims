require 'sketchup.rb'
require 'extensions.rb'

module KG
  module ArchDims
    VERSION = '1.3.2' unless defined?(VERSION)
    unless file_loaded?(__FILE__)
      ext = SketchupExtension.new('건축 치수 사전', 'kg_arch_dims/main')
      ext.description = '인체치수, 법정 최소·최대 치수, 설계 권장 치수를 검색하는 창'
      ext.version = VERSION
      ext.creator = 'Go Geon'
      Sketchup.register_extension(ext, true)
      file_loaded(__FILE__)
    end
  end
end
